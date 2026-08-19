# Research: Pilos 일별 문서 증분 집계 및 보고서 자동 갱신 동기화

## Decision 1: `select_pending_daily_document_targets` 쿼리 수정 및 최적화

### Context
`pilos/storage/daily_document_db.py` 내부의 `select_pending_daily_document_targets` 함수는 어떤 `(stock_id, model_date)`가 새로운 일별 문서를 생성해야 하는지 판정합니다.

### Current Query Problem
```sql
SELECT DISTINCT
    pc.stock_id,
    DATE(pc.created_at) AS model_date
FROM tokenized_comment AS tc
INNER JOIN preprocessed_comment AS pc
    ON pc.preprocessed_comment_id = tc.preprocessed_comment_id
WHERE tc.tokenizer_version = :tokenizer_version
  AND TIME(pc.created_at) < :market_close_time
  AND NOT EXISTS (
      SELECT 1
      FROM daily_document AS dd
      WHERE dd.stock_id = pc.stock_id
        AND dd.model_date = DATE(pc.created_at)
        AND dd.tokenizer_version = :tokenizer_version
  )
  AND NOT EXISTS (
      SELECT 1
      FROM daily_document_comment AS ddc
      WHERE ddc.tokenized_comment_id = tc.tokenized_comment_id
  )
ORDER BY model_date DESC, pc.stock_id ASC
```
- 문제점: `AND NOT EXISTS (SELECT 1 FROM daily_document AS dd ...)` 조건으로 인해, 하루 중 최초 1회(00:03) 일별 문서가 생성된 후에는 낮 동안 수만 건의 댓글이 추가 수집되어도 대상에서 영구 제외됨.

### Decision
- `NOT EXISTS (SELECT 1 FROM daily_document ...)` 조건을 제거한다.
- `daily_document_comment`에 아직 매핑되지 않은 토큰(`ddc.tokenized_comment_id IS NULL` 또는 `NOT EXISTS`)이 존재하는 종목·날짜를 감지하도록 변경한다.
- 400만 건 규모의 테이블에서 빠른 검색을 위해 `idx_daily_document_comment_tokenized` 인덱스를 활용하고, 최근 운영 기간(`DATE(pc.created_at) >= :min_date`) 필터를 적용하여 수 밀리초(ms) 단위로 고속 응답하도록 최적화한다.

---

## Decision 2: 일별 문서 스냅샷 및 매핑의 불변성 보존 (Immutability & Idempotency)

### Context
`docs/work/archive/이주광.md` 및 `pilos_v2.sql`에 정의된 아키텍처 원칙에 따라 기존 `daily_document` 레코드를 `UPDATE`하지 않고 새 행을 `INSERT`해야 합니다.

### Decision
- `insert_daily_document_with_comments`의 기존 로직을 유지한다.
- 토큰 집합이 동일하면 `document_hash`가 같으므로 기존 `daily_document_id`를 반환하고,
- 신규 댓글이 추가되면 새로운 `document_hash`와 함께 새 `daily_document_id`가 생성되며, `daily_document_comment`에 새 스냅샷과의 매핑이 추가된다.
- 매핑 적재 완료 후에는 해당 토큰들이 `daily_document_comment`에 존재하므로 다음 배치에서는 자동으로 0건으로 안정화된다.

---

## Decision 3: 다운스트림 Ridge 모델 추론 및 LLM 보고서 갱신 연계

### Context
신규 일별 문서 스냅샷(`daily_document_id`)이 생성되었을 때 후속 단계들이 이를 감지하고 지표를 갱신해야 합니다.

### Decision
- **모델 추론 (`run_database_inference`)**:
  - `select_inference_document_records` 쿼리가 각 `(stock_id, model_date)`의 가장 큰 `daily_document_id`를 조회하므로, 새로 생성된 스냅샷에 대해 즉시 긍정/부정 Ridge 회귀 추론이 수행되어 `sentiment_index_result`에 적재된다.
- **LLM 보고서 (`run_pending_llm_report_generation`)**:
  - `_process_target`에서 최신 `daily_document_id` 및 신호 수치로 `calculate_report_input_hash(request)`를 계산한다.
  - 문서 ID와 댓글 수, 점수가 변경되면 `input_hash`가 달라지므로 기존 캐시(`existing`)를 거치지 않고 보고서 생성(`generated`) 또는 수급 갱신(`updated`)으로 자동 처리된다.
