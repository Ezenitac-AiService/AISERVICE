# Interface Contracts: A-Team Pilos 댓글 크롤링 및 파이프라인 정합성 복원

**Feature**: `023-pilos-crawler-collection-audit`
**Date**: 2026-08-20

---

## 1. Internal Crawler Engine Contract (`pilos.collection.comment_crawler`)

### `_select_page(comments: list[dict], seen_ids: set, should_stop: callable)`
- **Input**:
  - `comments`: 토스 커뮤니티 API 응답 내 댓글 딕셔너리 리스트
  - `seen_ids`: 현재 실행 내 중복 방지 세트
  - `should_stop`: 종료 조건 검사 콜백 (`commentId <= end_before_id` 또는 하한 날짜 초과 시 `True`)
- **Behavior**:
  1. 각 댓글에 대해 `commentId`가 존재하면 유효한 댓글로 처리하고 `last_cursor = cid`를 반드시 갱신한다.
  2. `authorUserProfileId`가 누락된 경우 `"ANONYMOUS_USER"`로 치환 후 SHA-256 해시를 생성한다.
  3. `nickname`이 누락된 경우 `"익명"`으로 치환 후 SHA-256 해시를 생성한다.
  4. 하위 대댓글(`replies`, `subComments`)이 존재할 경우 각각을 평탄화하여 `new_comments`에 포함한다.
  5. `should_stop(comment)` 판정 시 즉시 `(last_cursor, True, new_comments)`를 반환한다.
- **Output**: `tuple[int | None, bool, list[dict]]` (`(last_cursor, stopped, new_comments)`)

---

## 2. Catch-up Backfill CLI Contract (`pilos.jobs.backfill_comments`)

### Command Invocation
```bash
python -m pilos.jobs.backfill_comments --until-date 2026-08-18 --target all
```

- **Arguments**:
  - `--until-date YYYY-MM-DD`: 백필 수집 목표 하한 일자 (기본값: `2026-08-18`)
  - `--target {sk,others,all}`: 수집 대상 종목 (`sk`=SK하이닉스만, `others`=그 외 8개, `all`=10개 전체)
- **Exit Code**:
  - `0`: 10개 전 종목 정상 백필 완료 (`status == 'done'`)
  - `1`: 1개 이상의 종목에서 중단 또는 예외 발생

---

## 3. End-to-End Pipeline Cascade Contract (`pilos.jobs.run_service_pipeline`)

### Function: `run_full_backfill_and_cascade(until_date: str = "2026-08-18") -> PipelineRunSummary`
- **Execution Flow**:
  1. **Stage 1 (Backfill Collection)**: 10개 전 종목 18~19일 결손 데이터 백필 수집
  2. **Stage 2 (Comment Preprocessing)**: 신규 수집된 JSONL 파일의 `preprocessed_comment` 적재
  3. **Stage 3 (Kiwi Tokenization)**: 미토큰화 댓글 형태소 분석 및 `tokenized_comment` 적재
  4. **Stage 4 (Daily Documents)**: 18일, 19일 일별 감성 코퍼스 문서 갱신
  5. **Stage 5 (Supply & Demand)**: 키움 수급 지표 연동
  6. **Stage 6 (Ridge Model Inference)**: 감성지수 및 상승 확률 예측
  7. **Stage 7 (v13 LLM Report Generation)**: 10개 종목 일별 AI 종합 분석 보고서 생성
