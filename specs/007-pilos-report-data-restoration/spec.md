# Feature Specification: 007-pilos-report-data-restoration

**Feature Branch**: `007-pilos-report-data-restoration`
**Created**: 2026-08-18
**Status**: Draft
**Input**: User description: "pilos의 db 덤프에서 복원할때에, 분석자료와 보고서를 누락했어? 오른쪽 위에 보면, 이전 일자를 선택하였고 '데이터가 있는 날짜만 선택가능'이라고 표시되어있지? 그런데 데이터가 안나와"

---

## Executive Summary & Background

Pilos Stock Lab (`/ateam/pilos/`) provides sentiment-based supply/demand analytics and LLM-generated market commentary reports for KOSPI 10 stocks. 

The original database dump (`pilos_v2.sql`) contains complete historical sentiment index calculations (786 rows in `sentiment_index_result`) and fully synthesized market commentary reports (882 rows in `llm_report`). However, on the stock detail page (`/stocks/<stock_code>`), when users select valid historical dates (e.g. `2026-08-11`), the interface displays empty dashes (`—`), "저장된 시장 해설이 없습니다", and "추론 대기 중" (HTTP 202 `inference_pending`).

### Root Cause Identification
1. **Unconstrained Background Worker Ingestion**: When `pilos-worker` container booted, its daemon executed `build_daily_documents` across all historical raw comments. Because `daily_document_comment` mapping was not pre-populated in the dump, the worker generated ~1,638 redundant `daily_document` records (IDs 5970+) with empty sentiment and LLM analysis.
2. **Query Shadowing by Latest Document ID**: Pilos storage queries (`_SELECT_LATEST_DOCUMENT`, `_SELECT_DETAIL_SENTIMENT_INDEXES_BY_STOCK_CODE`) resolved documents by `ORDER BY daily_document_id DESC LIMIT 1` / `newer_document.daily_document_id > d.daily_document_id`. Consequently, the empty worker-created documents shadowed the genuine documents (IDs <= 5969) that contained all sentiment analysis and LLM reports.
---

## Clarifications

### Session 2026-08-18
- Q: Pilos 서비스의 데이터 정합성을 위해 백그라운드 워커(pilos-worker)의 동작 방식과 과거 미추론 문서를 어떻게 정리할까요? → A: 워커에 기존 완료 일자 스킵(Idempotent) 로직 적용 + 중복 미추론 문서 정리 + 저장소 쿼리 강화 (분석 완료된 문서 우선 조회)

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Historical Stock Report & Commentary (Priority: P1)

As an investor using Pilos Stock Lab, when I navigate to a stock detail page (e.g., 현대차 `005380`) and pick a historical date with available data (e.g., `2026-08-11`), I want to see the complete LLM market commentary report, actual supply/demand indices, and positive/negative model analysis rather than placeholder dashes or "추론 대기 중".

**Why this priority**: Core value proposition of Pilos is providing actionable AI analysis and sentiment metrics for selected dates.

**Independent Test**:
- Navigate to `http://localhost:8080/ateam/pilos/` -> Select `현대차 (005380)`.
- Change the date selector to `2026-08-11`.
- Verify the LLM report displays the complete synthesized market commentary, direction badge, signal score, and positive/negative keyword contributions without HTTP 202 errors.

**Acceptance Scenarios**:
1. **Given** stock `005380` on date `2026-08-11`, **When** the user loads the stock detail view, **Then** the LLM report section displays full commentary, conclusion, and supply/demand index metrics.
2. **Given** a historical trading date with analyzed data, **When** `GET /api/stocks/005380/llm-reports?model_date=2026-08-11` is called, **Then** it returns HTTP 200 OK with the parsed report JSON instead of HTTP 202 `inference_pending`.

---

### User Story 2 - Resilient Document Resolution in Storage Layer (Priority: P2)

As a system engineer, I want the Pilos storage layer to prioritize documents with completed sentiment analysis and LLM reports over un-inferred empty documents when duplicate `(stock_id, model_date)` snapshots exist, so that background ingestion cannot invalidate existing reports.

**Why this priority**: Prevents background batch processing or re-tokenization from ever breaking user-visible reports.

**Independent Test**:
- Verify SQL queries in `llm_report_storage.py` and `sentiment_index_storage.py` prioritize rows that have matching `sentiment_index_result` and `llm_report` entries.

**Acceptance Scenarios**:
1. **Given** multiple `daily_document` rows for `(stock_id, model_date)`, **When** querying for detail sentiment and LLM reports, **Then** the query selects the document record that has existing completed `sentiment_index_result` and `llm_report` rows.

---

### User Story 3 - Clean Date Picker Navigation (Priority: P3)

As a user browsing stock history, I want the date picker to only navigate through trading dates that have actionable analysis data, preventing navigation into un-analyzed empty dates.

**Why this priority**: Improves user experience by avoiding confusion when clicking previous/next dates.

**Independent Test**:
- Check the date picker count and hint text on the stock detail page (`/stocks/005380`).

**Acceptance Scenarios**:
1. **Given** stock `005380`, **When** clicking next/previous date buttons, **Then** every selectable date renders non-empty sentiment indices and reports.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST return HTTP 200 OK with full market commentary and sentiment metrics for any date having an existing `llm_report` in the database.
- **FR-002**: The storage layer MUST prioritize `daily_document` records that contain completed `sentiment_index_result` and `llm_report` entries over un-inferred duplicate snapshots.
- **FR-003**: The database cleanup MUST remove or consolidate orphaned `daily_document` records (created by redundant worker runs) so that historical analysis data is cleanly referenced.
- **FR-004**: The background worker (`pilos-worker`) MUST NOT insert duplicate `daily_document` records for historical dates that already have completed daily documents.
- **FR-005**: The web interface MUST display the correct supply direction, signal score, commentary text, and model card metrics for all 10 stocks across all available historical dates.

### Key Entities

- **`daily_document`**: Represents a daily collection of tokenized comments for a given stock and date (`stock_id`, `model_date`, `comment_count`).
- **`sentiment_index_result`**: Represents the Ridge model sentiment scores and keyword contributions calculated from a daily document (`daily_document_id`, `artifact_id`, `supply_demand_association_score`, `positive_contribution_keywords`, `negative_contribution_keywords`).
- **`llm_report`**: Represents the synthesized LLM commentary report for a stock and date (`stock_id`, `model_date`, `daily_document_id`, `report_json`, `status`).
- **`supply_demand`**: Represents actual exchange trading volume and supply/demand index (`stock_id`, `trade_date`, `supply_demand_index`, `buy_volume`, `sell_volume`).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of historical dates containing existing `llm_report` records return HTTP 200 OK and render commentary text without "저장된 시장 해설이 없습니다" or "추론 대기 중".
- **SC-002**: For `현대차` (005380) on `2026-08-11`, the stock detail page displays complete positive/negative model parameters, keywords, and market commentary.
- **SC-003**: Zero HTTP 202 `inference_pending` responses for dates with completed dump reports across all 10 KOSPI stocks.
- **SC-004**: Full 10/10 PASS on `verify_e2e_services.ps1` diagnostic suite.

---

## Assumptions

- The database dump `pilos_v2.sql` contains the ground-truth historical reports (882 rows) and sentiment indices (786 rows).
- Duplicate un-inferred `daily_document` records created during container startup can be safely cleaned up.
- `pilos-worker` should be configured with idempotent target selection so that it does not repeatedly recreate historical daily documents.
