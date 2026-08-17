# Implementation Plan: 007-pilos-report-data-restoration

**Branch**: `007-pilos-report-data-restoration` | **Date**: 2026-08-18 | **Spec**: [spec.md](spec.md)

## Summary

Restore full visibility of historical sentiment index metrics and LLM market commentary reports across Pilos Stock Lab (`/ateam/pilos/`). Eliminate query shadowing by making SQL resolution prioritize analyzed document snapshots over empty un-inferred documents, prune redundant worker-created `daily_document` records, enforce worker idempotency, and filter date picker navigation to dates with actionable data.

---

## Technical Context

**Language/Version**: Python 3.12, JavaScript (ES6), SQL (MySQL 8.0)
**Primary Dependencies**: Flask, SQLAlchemy, MySQL Connector, Gunicorn
**Storage**: MySQL 8.0 (`pilos_v2` database)
**Testing**: Python `unittest`, PowerShell E2E diagnostic test suite (`verify_e2e_services.ps1`)
**Target Platform**: Docker containerized stack behind Nginx Gateway (`aiservice-gateway`)
**Project Type**: Full-stack Financial Sentiment Analytics Web Service

---

## Constitution Check

- ✅ **Constitution Gate 1 (Single Port Gateway Integrity)**: All Pilos endpoints remain accessed through `:8080` / `:80` without exposing private container ports directly.
- ✅ **Constitution Gate 2 (No Unverified Mock Data)**: Ground-truth data from `pilos_v2.sql` (882 LLM reports, 786 sentiment index records) is restored and preserved.
- ✅ **Constitution Gate 3 (Subsystem Encapsulation)**: Changes are strictly confined to A-Team (`ateam/pilos-sentiment-index`) and database migration scripts.

---

## Proposed Changes

### Phase 1: Database Pruning & Resilient Storage Queries

#### [ateam/pilos-sentiment-index/pilos/storage/llm_report_storage.py](file:///c:/AISERVICE/ateam/pilos-sentiment-index/pilos/storage/llm_report_storage.py)
- Update `_SELECT_LATEST_DOCUMENT` and `_SELECT_LLM_REPORT` to prioritize documents that have corresponding `sentiment_index_result` and `llm_report` entries.

#### [ateam/pilos-sentiment-index/pilos/storage/sentiment_index_storage.py](file:///c:/AISERVICE/ateam/pilos-sentiment-index/pilos/storage/sentiment_index_storage.py)
- Update `_SELECT_DETAIL_SENTIMENT_INDEXES_BY_STOCK_CODE` so that when multiple daily documents exist for a date, the document with matching `sentiment_index_result` is selected.

#### [ateam/pilos-sentiment-index/pilos/storage/daily_document_db.py](file:///c:/AISERVICE/ateam/pilos-sentiment-index/pilos/storage/daily_document_db.py)
- In `select_pending_daily_document_targets`, check `NOT EXISTS (SELECT 1 FROM daily_document dd WHERE dd.stock_id = pc.stock_id AND dd.model_date = DATE(pc.created_at))` to make daily document generation idempotent.

#### [ateam/pilos-sentiment-index/scripts/cleanup_orphaned_documents.py](file:///c:/AISERVICE/ateam/pilos-sentiment-index/scripts/cleanup_orphaned_documents.py)
- Implement a standalone cleanup script to prune un-inferred duplicate `daily_document` records (IDs > 5969).

---

## Verification Plan

### Automated Tests
```bash
# 1. Verify LLM report Python service layer
docker compose exec pilos_web python -c "
from datetime import date
from pilos.service.llm_report_service import get_llm_report_for_display
res = get_llm_report_for_display('005380', date(2026, 8, 11))
assert res.get('status') == 'ready'
print('SUCCESS:', res.get('market_commentary')[:60])
"

# 2. Run E2E Test Suite
powershell -ExecutionPolicy Bypass -File specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1 -Mode Local
```

### Manual Verification
- Access `http://localhost:8080/ateam/pilos/stocks/005380` in browser.
- Select `2026-08-11`.
- Verify the LLM report displays complete commentary text, supply direction, and signal score without dashes or "추론 대기 중".
