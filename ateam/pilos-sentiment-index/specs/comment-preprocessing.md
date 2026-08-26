# 댓글 전처리 기능 명세

## 상태

- 구현 상태: 구현 완료, 후속 토큰화 입력으로 사용 중
- 검증 상태: 전처리 wiring·부분 실패 자동 테스트와 실제 최상위 실행 확인.
  2026-08-10 실행에서 14,227건, 다음 증분에서 384건 적재
- 통합 상태: `main@f80fdc2` 반영 완료 (PR #3, #17)

## 목적

크롤링 원본 댓글을 분석 영역이 재사용할 수 있는 표준 댓글 DataFrame으로
변환한다. 현재 기능은 파일 기반 원본 처리에 사용되며, 실시간 크롤링
작업에서도 같은 분석 함수와 데이터 계약을 재사용하는 기반이다.

## 범위

포함 범위는 다음과 같다.

- 외부 중첩 레코드를 표준 댓글 컬럼으로 평탄화
- 식별자, 종목코드와 댓글 시각 정규화
- 제목과 본문을 분석용 `text`로 결합
- 이모지·비-BMP 문자 제거와 반복형 소셜 표현 정규화
- 필수값·빈 텍스트 제거, `comment_id` 중복 제거와 정렬
- 원본 파일별 전처리 결과 DB 적재
- 단일 댓글 추론에서 재사용할 문자열 전처리

실시간 수집 주기, 크롤링 재시도, 최상위 실행 순서와 수집 완료 상태는
이 기능의 범위가 아니다.

## 입력과 출력

원본 레코드에서 다음 값을 읽는다.

| 원본 위치 | 전처리 컬럼 |
|---|---|
| `commentId` | `comment_id` |
| `message.title` | `title` |
| `message.message` | `message` |
| `board.stockCode` | `stock_code` |
| `statistic.likeCount` | `like_count` |
| `parentId` | `parent_id` |
| `createdAt` | `created_at` |
| `updatedAt` | `updated_at` |
| `raw_line_number` | `raw_line_number` |

전처리 완료 DataFrame은 위 컬럼과 분석 문자열 `text`를 유지한다. DB
적재 직전에 실행기가 `stock_id`, `source_comment_file_id`를 추가한다.
`raw_line_number`와 두 DB 식별자는 원본 추적·저장을 위한 값이며 공통
댓글 의미 계약을 확장하지 않는다.

## 실행 흐름

현재 파일 기반 실행은 다음 순서다.

```text
source_comment_file 미처리 파일 조회
→ JSONL 레코드 순회
→ records_to_comment_dataframe
→ normalize_comment_dataframe
→ preprocess_comments
→ stock_id·source_comment_file_id 추가
→ preprocessed_comment INSERT
```

공식 실행 모듈은 `pilos.jobs.preprocess_comments` 하나다. 미처리 파일 전체는
`run_pending_comment_preprocessing()`, 이번 수집에서 기록된 파일만 처리할 때는
`run_preprocessing_for_files()`, 파일 하나의 순수한 가공 흐름은
`run_comment_preprocessing()`을 사용한다. 실행 함수는 `PreprocessRunSummary`를
반환한다(아래 '실패와 재실행').

## 전처리 규칙

- `comment_id`, `parent_id`는 값이 있으면 문자열로 변환한다.
- `stock_code`의 `A` 접두사를 제거하고 여섯 자리 문자열로 맞춘다.
- 댓글 시각은 입력 시각을 이동하지 않고 timezone 정보와 마이크로초를
  제거한 `datetime`으로 정규화한다. 입력은 KST 의미를 가져야 한다.
- 제목과 본문이 같거나 한쪽이 다른 쪽의 시작 부분이면 중복된 부분을
  한 번만 사용한다. 그 외에는 공백 한 칸으로 연결한다.
- 비-BMP 문자, 이모지 조합 문자와 유니코드 줄 구분자는 공백으로 바꾼다.
- `ㅋㅋ`, `ㅠㅠ`·`ㅜㅜ`, `ㅡㅡ`, `ㄷㄷ` 계열 표현은 각각
  `소셜웃음`, `소셜울음`, `소셜짜증`, `소셜놀람`으로 정규화한다.
- `comment_id`, `stock_code`, `text`, `created_at`, `updated_at`이 결측인
  행과 빈 `text` 행을 제거한다.
- 같은 `comment_id`가 여러 개면 `updated_at`, `created_at` 기준으로
  마지막 행을 남긴다.
- 결과를 `created_at`, `comment_id` 순서로 정렬한다.

`preprocess_comment_text()`는 단일 댓글에 같은 이모지 제거와 소셜 표현
정규화를 적용한다. 제목·본문 결합과 행 단위 결측·중복 처리는 수행하지
않는다.

## 실패와 재실행

- 파일 하나의 조회·변환·적재 실패는 실행기가 로그로 남기고 다음 파일을
  계속 처리한다.
- 반환값은 `PreprocessRunSummary`(처리 대상 파일 수 `total`, 적재 건수 `inserted`,
  실패 파일 수 `failed`, 실패 파일명 `failed_files`)이다. 파일 하나가 실패해도
  다음 파일을 계속 처리하고, 실패 사실을 반환값에 남긴다.
- 최상위 실행기는 `summary.failed > 0`으로 부분 실패를 감지하고 뒤 단계를
  중단한다.
- 이 `PreprocessRunSummary` 반환 계약은 PR #5를 통해 `develop`에 반영됐다.
- 독립 CLI의 `main()`은 실패 수를 로그로 남긴다. 운영 최상위 실행기는 CLI
  종료 코드에 의존하지 않고 `PreprocessRunSummary.failed`를 직접 검사해
  부분 실패 시 뒤 단계를 중단한다.
- DB 적재는 파일별 한 트랜잭션에서 `INSERT IGNORE`로 수행한다.

## 검증과 완료 기준

현재 구현은 후속 토큰화와 일별 문서 생성에 사용된 실제 DB 데이터와
최상위 실행으로 확인됐다. 자동 테스트는 파일별 실패 격리, 반환 요약과
수집→전처리 연결을 검증한다.

완료 기준은 표준 컬럼 생성, 정규화·텍스트 결합·중복 제거, DB 적재와
단일 댓글 문자열 전처리 함수가 존재하는 것이다. 실시간 실행 통합은
별도 기능의 완료 기준으로 관리한다.

## 관련 코드와 정본

- [`pilos/analysis/preprocessor.py`](../pilos/analysis/preprocessor.py)
- [`pilos/storage/normalization.py`](../pilos/storage/normalization.py)
- [`pilos/jobs/preprocess_comments.py`](../pilos/jobs/preprocess_comments.py)
- [`pilos/storage/preprocess_db.py`](../pilos/storage/preprocess_db.py)
- [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
