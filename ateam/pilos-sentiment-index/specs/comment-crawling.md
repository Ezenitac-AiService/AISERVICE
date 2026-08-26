# 댓글 수집(크롤링) 기능 명세

## 상태

- 구현 상태: 백필·증분 수집, 작성일별 JSONL 저장, 매니페스트 상태 관리,
  원본 파일 DB 등록, 최상위 수집→전처리 연결, 종목 타겟 CLI 구현 완료
- 검증 상태: 백필·증분·매니페스트 자동 테스트와 실제 최상위 실행 확인.
  2026-08-10 실행에서 실제 토스 API·DB로 15,283건, 다음 증분에서 438건 수집
- 통합 상태: `main@f80fdc2` 반영 완료 (PR #5, #17)
- 자동화 상태: 최상위 실행기가 `run_incremental()` 요약을 받아 부분 실패 시
  전처리 이후 단계로 진행하지 않음(PR #14)

## 목적

토스 종목 토론 댓글을 외부 API에서 가져와 **원본 그대로 JSONL로 보존**한다.
과거 이력을 채우는 백필과 직전 수집 이후 새 댓글만 긁는 증분 두 모드를 제공하고,
수집 상태(커버리지·최신 지점)를 매니페스트로 추적한다. 원본 JSONL이 진실원본이며
DB(`preprocessed_comment`)는 그 파생본이다.

전처리 자체는 [`comment-preprocessing.md`](comment-preprocessing.md)가 담당한다.
이 문서는 원본을 만드는 **수집**과, 수집물을 전처리로 넘기는 **조합 실행**을 다룬다.

## 범위

포함 범위는 다음과 같다.

- 백필 수집: 최신에서 하한 날짜까지 과거로 페이지네이션
- 증분 수집: 직전 실행 최신 지점(`recent_comment_id`) 이후 새 댓글만
- 증분 경계 시드: 경계가 없을 때 기존 파일에서 초기화
- 댓글 `createdAt` 날짜별 JSONL 파일 라우팅과 원본 보존 append
- 파일 꼬리 dedup, 잘린 줄 봉인, 재개 커서 저장
- 매니페스트: 일별 카운트, 최신 지점, 커버리지 날짜 공백 점검
- 원본 파일 메타데이터를 `source_comment_file`에 등록
- 종목 타겟 선택 CLI(`--target sk|others`)와 백필 하한 날짜 CLI
- 최상위 운영 실행기의 증분 수집→기록 파일 전처리 연결

제외 범위는 다음과 같다.

- 표준 컬럼 변환·정규화·중복 제거·DB 적재 규칙(전처리 명세 소관)
- 시장 수급(매수/매도) 데이터 수집
- 키움 실시간 체결(`0B`) 수집 — 과거 소급 불가로 보류
- 주기 실행 스케줄러 설정 자체(운영 환경에서 별도 구성)

## 입력과 출력

수집 대상 종목은 상수가 아니라 DB에서 읽는다. `CommentDB.select_stock()`이
`(stock_id, 종목명, subjectId)` 행을 반환하고, 실행기가 타겟에 따라 거른다.

외부 응답의 개별 댓글 레코드는 **변형 없이** JSONL 한 줄로 저장한다. 저장 시
각 레코드의 물리적 줄 번호가 곧 `raw_line_number`가 되며(전처리 watermark의 기준),
이는 원본 파일이 append-only라는 전제에서 성립한다.

출력 파일 경로는 다음과 같다.

| 모드 | 경로 | 생성 함수 |
|---|---|---|
| 백필 | `data/raw/until_{하한날짜}_{종목}_comment.jsonl` | `json_io.get_comment_file` |
| 증분 | `data/raw/from_{작성일}_{종목}_comment.jsonl` | `json_io.get_incremental_comment_file` |

수집 상태는 매니페스트에 저장한다(별도 파일 없이 `modes.backfill.cursor`/`.status`,
`modes.incremental.recent_id`, 일별 카운트). 원본 파일 메타데이터는
`source_comment_file` 테이블에 등록한다(`stock_id`·`file_path`·`file_name`·
`file_ext`·`platform`).

## 실행 흐름

의존 방향은 항상 `jobs → collection / storage` 한 방향이다. 실행기는 직접
수집·저장하지 않고 수집 엔진과 저장·상태 계층을 조합한다.

**백필** — `pilos.jobs.backfill_comments`

```text
select_stock → 타겟 필터(sk|others)
→ crawl_until_date(종목, until_ 파일, stop_when)
   ├ seal_trailing_newline / load_seen_comment_ids
   ├ load_backfill_cursor(재개 지점)
   ├ 페이지 루프: fetch → append_comments → save_backfill_cursor(매 페이지)
   └ 하한 날짜 도달 시 종료
→ manifest.record_run / find_coverage_gaps
→ insert_source(원본 파일 등록)
```

**증분** — `pilos.jobs.incremental_comments`

```text
select_stock → 타겟 필터(sk|others)
→ _seed_recent_boundary(경계 없으면 초기화)
→ crawl_from_now(종목, 날짜별 out_file_for)
   ├ load_recent_id(종료 경계)
   ├ 최신순 페이지 루프: fetch → DatePartitionedAppender.append
   └ 경계 도달/이력 소진 시 종료
→ manifest.update_from_files(파일 스캔 self-heal) / find_coverage_gaps
→ insert_source(작성일별 파일마다 등록)
```

**운영 조합** — `pilos.jobs.run_service_pipeline`이 `run_incremental()`의
`recorded_files`를 `run_preprocessing_for_files()`에 직접 전달한다. 초기 원본
등록과 전체 미처리 전처리는 `pilos.jobs.maintenance.initialize_comment_data`를
명시적으로 실행할 때만 수행한다.

전처리 대상 파일 선택은 `select_source_files_with_watermark(include_backfill)`이
정한다. 기본값 `False`는 `from_` 증분 파일만 처리해, 백필 종료 후 정적인 `until_`
파일의 매 실행 재스캔 비용을 없앤다. 초기화 유지보수 명령은
`include_backfill=True`로 `until_`까지 포함한다. 이 파일 선택은 수집과
전처리의 경계 동작이며, 전처리 규칙 자체는 [`comment-preprocessing.md`]
(comment-preprocessing.md) 소관이다.

## 핵심 처리 규칙

- **증분 경계 확정은 정상 종료 시에만**(P0-1). fetch 실패·커서 정지 등
  중단(interrupted) 상태에서는 `recent_comment_id`를 앞당기지 않는다. 그래서
  다음 실행이 빠진 구간을 다시 긁고, 겹침은 dedup으로 흡수한다.
- **증분 경계 시드 우선순위**: (1) `from_` 작성일 최신 파일의 전체 최댓값
  commentId(`max_comment_id` — from_ 파일은 여러 증분분이 이어 붙어 첫 줄이
  최신이 아닐 수 있으므로 최댓값 사용), (2) 없으면 `until_*` 백필 파일의 최신 id.
- **백필 재개 커서를 매 페이지 저장**하고 완료/중단 상태를 구분 저장(P1-1)해
  중단 지점부터 이어받는다.
- **작성일별 파일 라우팅**: `DatePartitionedAppender`가 `createdAt` 날짜로
  파일을 나눠 append하며, 파일 꼬리 window만 로드해 실행 내 중복을 막는다(P2-1).
- **잘린 줄 봉인**: 이전 크래시로 개행 없이 잘린 마지막 줄을 개행으로 격리한다(P1-3).
- **종목 타겟 필터**: `--target sk`는 `SK_HYNIX_ID` 종목만, `--target others`는
  그 외 전체. 이름 문자열이 아니라 subjectId로 판별한다. 백필은 추가로
  `--until-date YYYY-MM-DD`(기본 `RESUME_UNTIL_DATE`)를 받는다.
- **재시도**: 429 `Retry-After` 존중, 최대 `MAX_RETRY`회. 커서가 직전과 같으면
  무한 루프 방지로 종료한다.

## 실패와 재실행

- **종목별 오류 격리**: 한 종목 수집이 예외로 끝나도 나머지 종목은 계속한다.
- **부분 실패 감지용 반환값(증분)**: 증분 실행기는 `run_incremental(target)`이
  `IncrementalRunSummary`(대상 종목 수 `total`, 성공 `succeeded`, 실패 `failed`,
  수집 건수 `collected`, 실패 사유 목록 `failures`)를 반환해 프로그램 호출자가
  부분 실패를 판단한다. CLI·스케줄러용 `main(target)`은 기존 호환을 위해
  `summary.exit_code`(`done`이 아닌 종목이 하나라도 있으면 1, 전부 성공이면 0)만
  반환한다.
- **부분 실패 감지용 종료 코드(백필)**: 백필 실행기는 `done`이 아닌 종목이
  하나라도 있으면 종료 코드 1을 반환한다(스케줄러가 실패를 감지하도록).
- **최상위 단계 중단**: 최상위 실행기는 수집 실패 또는 전처리 파일 부분 실패
  (`PreprocessRunSummary.failed > 0`, [`comment-preprocessing.md`](comment-preprocessing.md)
  참조) 시 뒤 단계를 실행하지 않고 실패 상태를 반환한다.
- **DB 등록 격리**: `insert_source` 실패는 로그로 남기고 원본 수집을 막지 않는다.
  DB 접속/스키마 준비 실패 시 그 실행은 JSONL만 저장하고 계속한다.
- **재실행 안전성**: 증분은 경계 이후만, 백필은 재개 커서 이후만 다시 긁는다.
  원본은 append-only이므로 중복은 dedup·전처리 단계 `comment_id` 기준으로 흡수된다.
- **커버리지 공백**: coverage 구간에 0건 날짜가 있으면 WARNING을 남긴다(휴리스틱).
  자동 재수집 트리거는 미구현.

## 검증 내용과 검증하지 않은 내용

검증한 내용:

- `tests/collection/test_crawl_incremental.py` — 증분 경계 확정(P0-1),
  경계 시드(from_ 최댓값·백필 폴백), dedup, 기록 파일 반환 등
- `tests/collection/test_crawl_backfill.py`, `test_manifest.py` — 백필·매니페스트
- 위 테스트는 `_fetch_comments`(네트워크)와 저장 경로(`json_io.DATA_DIR`)를 mock한다

추가 검증이 필요한 내용:

- 크롤러 실패 경로(429/5xx/파싱 실패/빈 응답/커서 정지) 자동 테스트 보강 필요
- append-only 전제 위반(중간 줄 삭제·재정렬) 감지 장치 없음

## 후속 소비자와 영향

- 수집 원본 JSONL과 `source_comment_file` 등록은 [`comment-preprocessing.md`]
  (comment-preprocessing.md)의 입력이 된다. 전처리는 `raw_line_number` watermark로
  새 줄만 처리하므로, 수집이 append-only를 지키는 것이 전처리 정합성의 전제다.
- 이후 토큰화·일별 문서·모델 단계는 전처리 결과(`preprocessed_comment`)를 소비한다
  (각 기능 명세 참조).
- 주기 실행은 저장소 루트 `run_service_pipeline.bat`가 최상위 실행기를 호출해
  수집→전처리를 잇는다. 종목 타겟 CLI는 단독 진단·운영에 사용할 수 있다.

## 남은 통합 과제

- 크롤러 429·5xx·파싱 실패·빈 응답·커서 정지 자동 테스트를 보강해야 한다.
- 매니페스트의 날짜 공백은 WARNING만 남기며 자동 재수집하지 않는다.
- `raw_line_number` watermark는 원본 파일의 append-only 전제에 의존하며
  중간 줄 삭제·재정렬을 감지하지 않는다.
- 전체 자동화와 실행 관측성은 [`service-pipeline-automation.md`]
  (service-pipeline-automation.md)에 적용 완료됐다.

## 관련 코드와 정본

- [`pilos/collection/comment_crawler.py`](../pilos/collection/comment_crawler.py)
- [`pilos/collection/constants.py`](../pilos/collection/constants.py)
- [`pilos/storage/comment_store.py`](../pilos/storage/comment_store.py)
- [`pilos/storage/manifest.py`](../pilos/storage/manifest.py)
- [`pilos/storage/json_io.py`](../pilos/storage/json_io.py)
- [`pilos/storage/comment_db.py`](../pilos/storage/comment_db.py)
- [`pilos/jobs/backfill_comments.py`](../pilos/jobs/backfill_comments.py)
- [`pilos/jobs/incremental_comments.py`](../pilos/jobs/incremental_comments.py)
- [`pilos/jobs/preprocess_comments.py`](../pilos/jobs/preprocess_comments.py)
- [`pilos/jobs/run_service_pipeline.py`](../pilos/jobs/run_service_pipeline.py)
- [`pilos/jobs/maintenance/initialize_comment_data.py`](../pilos/jobs/maintenance/initialize_comment_data.py)
- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) · [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
