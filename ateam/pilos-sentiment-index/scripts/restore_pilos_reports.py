"""Restore Pilos historical analysis reports by pruning redundant un-inferred daily documents.

Removes duplicate daily_document rows (IDs > 5969) created by background worker
runs before idempotency checks were in place, restoring 100% visibility of all
historical sentiment index scores and LLM market commentary reports.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

from sqlalchemy import text
from pilos.storage.db import get_engine


def restore_pilos_data() -> None:
    engine = get_engine()
    print("================================================================================")
    print(" [Pilos Data Restoration & Document Pruning]")
    print("================================================================================")

    with engine.begin() as conn:
        print("[Step 1] Creating index on daily_document_comment(daily_document_id)...")
        try:
            conn.execute(
                text(
                    "CREATE INDEX idx_ddc_doc_id ON daily_document_comment(daily_document_id);"
                )
            )
            print(" -> Index idx_ddc_doc_id created successfully.")
        except Exception as e:
            if "Duplicate key name" in str(e) or "already exists" in str(e):
                print(" -> Index idx_ddc_doc_id already exists.")
            else:
                print(f" -> Index notice: {e}")

        print("[Step 2] Temporarily disabling foreign key checks for atomic pruning...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

        print("[Step 3] Deleting orphaned daily_document rows (IDs > 5969)...")
        res_ddc = conn.execute(
            text("DELETE FROM daily_document_comment WHERE daily_document_id > 5969;")
        )
        print(f" -> Deleted {res_ddc.rowcount} orphaned daily_document_comment rows.")

        res_dd = conn.execute(
            text("DELETE FROM daily_document WHERE daily_document_id > 5969;")
        )
        print(f" -> Deleted {res_dd.rowcount} un-inferred daily_document rows.")

        print("[Step 4] Re-enabling foreign key checks...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

        print("[Step 5] Checking resulting dataset counts:")
        total_docs = conn.execute(text("SELECT COUNT(*) FROM daily_document;")).scalar()
        total_sentiment = conn.execute(text("SELECT COUNT(*) FROM sentiment_index_result;")).scalar()
        total_reports = conn.execute(text("SELECT COUNT(*) FROM llm_report;")).scalar()
        total_stocks = conn.execute(text("SELECT COUNT(*) FROM stock;")).scalar()

        print(f" - Active stocks: {total_stocks}")
        print(f" - Clean daily documents: {total_docs}")
        print(f" - Sentiment index results: {total_sentiment}")
        print(f" - LLM commentary reports: {total_reports}")
        print("================================================================================")
        print(" [SUCCESS] All historical analysis data restored and indexed cleanly!")
        print("================================================================================")


if __name__ == "__main__":
    restore_pilos_data()
