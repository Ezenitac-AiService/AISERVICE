# Pipeline Contracts: Pilos 일별 문서 증분 집계 및 보고서 자동 갱신 동기화

## 1. 내부 파이프라인 인터페이스 계약

### `select_pending_daily_document_targets`
- **모듈**: `pilos.storage.daily_document_db`
- **인자**:
  - `tokenizer_version: str` (예: `"kiwi_ver1"`)
  - `market_close_time: datetime.time` (예: `time(15, 30)`)
  - `min_date: datetime.date | None` (선택적: 최근 운영 시작일, 기본값 `SERVICE_INFERENCE_START_DATE`)
- **반환값**: `list[dict[str, Any]]`
  - 각 항목: `{"stock_id": int, "model_date": date}`
- **계약 보장**:
  - `tokenized_comment` 중 `daily_document_comment`에 아직 매핑되지 않은 토큰이 1건 이상 존재하는 모든 `(stock_id, model_date)`를 반환한다.
  - 기존에 `daily_document`가 존재하더라도 미매핑 토큰이 남아있으면 제외하지 않는다.
  - 미매핑 토큰이 없는 경우 빈 리스트 `[]`를 반환한다.

---

### `run_daily_document_building`
- **모듈**: `pilos.jobs.build_daily_documents`
- **반환값**: `tuple[int, int]` (성공 건수, 실패 건수)
- **계약 보장**:
  - 감지된 대상별로 `select_tokenized_comments_for_day`를 호출하여 장 마감 전 전체 댓글을 취합한다.
  - 취합된 토큰으로 `create_daily_document_data`를 실행하고 `insert_daily_document_with_comments`로 적재한다.
  - 실패 건수가 0이면 파이프라인 후속 단계(Ridge 추론 ➔ LLM 보고서)로 정상 진행한다.

---

## 2. 웹 대시보드 및 API 계약 (`/api/stocks`)

- **엔드포인트**: `GET /api/stocks` 및 `GET /api/stocks/<stock_code>`
- **반환 필드 보장**:
  - `model_date`: 해당 종목의 가장 최신 `daily_document.model_date`
  - `comment_count`: 해당 종목의 가장 최신 `daily_document.comment_count`
  - `analysis_status`: `ready` (충분한 데이터 기반 정상 분석 완료), `insufficient_evidence` (10건 미만 등 근거 부족), `inference_pending` (장전 추론 대기) 등 6단계 상태
