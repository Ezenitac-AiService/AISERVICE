# Research Document: 007-pilos-report-data-restoration

## 1. Problem Investigation & Analysis

### 1.1 Document ID Shadowing Mechanism
- **Issue**: `_SELECT_LATEST_DOCUMENT` in `llm_report_storage.py` and `_SELECT_DETAIL_SENTIMENT_INDEXES_BY_STOCK_CODE` in `sentiment_index_storage.py` used `ORDER BY daily_document_id DESC LIMIT 1` / `newer_document.daily_document_id > d.daily_document_id`.
- **Finding**: When `pilos-worker` spawned on container startup, it generated new `daily_document` records with IDs 5970~7616. Because these new rows lacked `sentiment_index_result` and `llm_report` records, the queries selected the empty rows, causing the API to return HTTP 202 `inference_pending` and empty `—` fields in UI.
- **Decision**: Update storage queries to conditionally match documents that have existing `sentiment_index_result` and `llm_report` records, or select the best analyzed document for the requested date.

### 1.2 Orphaned Document Cleanup & Database Health
- **Issue**: The redundant background worker run inserted 1,638 un-inferred `daily_document` rows and millions of unneeded mapping rows.
- **Decision**: Create an idempotent SQL migration / cleanup script that removes `daily_document` rows where `daily_document_id > 5969` (or rows with zero sentiment results created during redundant runs) and restores clean indexing.
- **Alternatives Considered**:
  - Full DB re-import from `pilos_v2.sql`: Viable, but running targeted cleanup is faster and non-destructive to volume state.

### 1.3 Background Worker Idempotency
- **Issue**: `select_pending_daily_document_targets` checked `NOT EXISTS (SELECT 1 FROM daily_document_comment)`, which triggered full re-generation across all historical comments.
- **Decision**: Update `select_pending_daily_document_targets` in `pilos/storage/daily_document_db.py` to check `NOT EXISTS (SELECT 1 FROM daily_document dd WHERE dd.stock_id = pc.stock_id AND dd.model_date = DATE(pc.created_at) AND dd.tokenizer_version = :tokenizer_version)`. This guarantees idempotency so the worker will not re-create documents for dates that already have daily documents.

### 1.4 Date Picker Navigation UX
- **Issue**: The date picker in `detail.js` loaded all historical raw documents (561 dates) instead of filtering to dates with valid analysis.
- **Decision**: Update `get_stock_detail_sentiment_indexes` / `_SELECT_DETAIL_SENTIMENT_INDEXES_BY_STOCK_CODE` so that only dates with valid sentiment analysis or actual market data are returned in the history array, ensuring every selectable date has complete charts and reports.
