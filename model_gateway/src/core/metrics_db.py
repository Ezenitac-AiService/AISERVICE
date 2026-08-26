import os
import shutil
import sqlite3
import datetime
import logging
from typing import Dict, Any, List

logger = logging.getLogger("MetricsDB")

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "metrics.db")


class MetricsDB:
    """Manages SQLite metrics database with WAL mode, busy timeout, and auto-healing quarantine."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._is_in_memory = (self.db_path == ":memory:")
        if not self._is_in_memory:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        is_new_db = not self._is_in_memory and not os.path.exists(self.db_path)
        try:
            self._init_db()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
            logger.warning(f"[MetricsDB] Database corruption or operational error detected: {e}. Initiating auto-recovery quarantine.")
            self._quarantine_and_recreate_db()

        if is_new_db and not self._is_in_memory:
            try:
                from scripts.seed_db import seed_database
                seed_database(reset=False)
            except Exception:
                pass

    def _quarantine_and_recreate_db(self):
        """Quarantines malformed/corrupted DB and WAL/SHM files, then recreates a healthy DB instance."""
        if self.db_path == ":memory:":
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = os.path.dirname(self.db_path)
        base_name = os.path.basename(self.db_path)

        for ext in ["", "-wal", "-shm"]:
            src_file = self.db_path + ext
            if os.path.exists(src_file):
                src_base = os.path.basename(src_file)
                corrupt_file = os.path.join(target_dir, f"{src_base}.corrupt_{timestamp}")
                try:
                    shutil.move(src_file, corrupt_file)
                    logger.warning(f"[MetricsDB QUARANTINE] Moved corrupt file {src_file} -> {corrupt_file}")
                except Exception as move_err:
                    logger.error(f"[MetricsDB ERROR] Failed to quarantine corrupt file {src_file}: {move_err}")
                    try:
                        os.remove(src_file)
                    except Exception:
                        pass

        # Try recreating file-based DB
        try:
            self._init_db()
            logger.info("[MetricsDB RECOVERY] Successfully recreated fresh healthy MetricsDB instance.")
        except (sqlite3.DatabaseError, sqlite3.OperationalError, Exception) as rec_err:
            logger.error(f"[MetricsDB ERROR] Recreating file-based DB failed: {rec_err}. Falling back to In-Memory DB (:memory:).")
            self.db_path = ":memory:"
            self._is_in_memory = True
            self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns SQLite connection with WAL mode and timeout=10.0 per C2 critique."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            if not self._is_in_memory and self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
            conn.row_factory = sqlite3.Row
            return conn
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
            if not self._is_in_memory and self.db_path != ":memory:":
                logger.warning(f"[MetricsDB Connection ERROR] {e}. Triggering database recovery.")
                self._quarantine_and_recreate_db()
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                if not self._is_in_memory and self.db_path != ":memory:":
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA synchronous=NORMAL;")
                conn.row_factory = sqlite3.Row
                return conn
            raise

    def _init_db(self):
        """Creates tables and indexes if not exists."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_key_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    endpoint TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    ttft_ms REAL DEFAULT 0.0,
                    tps REAL DEFAULT 0.0,
                    is_error INTEGER DEFAULT 0,
                    prompt_text TEXT,
                    completion_text TEXT,
                    thinking_text TEXT
                );
            """)
            # Migration check for existing databases
            try:
                conn.execute("ALTER TABLE api_key_logs ADD COLUMN prompt_text TEXT;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE api_key_logs ADD COLUMN completion_text TEXT;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE api_key_logs ADD COLUMN thinking_text TEXT;")
            except Exception:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS playground_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playground_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    thinking_process TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES playground_sessions(id) ON DELETE CASCADE
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_key ON api_key_logs(api_key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON api_key_logs(timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON playground_messages(session_id);")
            conn.commit()

    def create_playground_session(self, session_id: str, title: str) -> Dict[str, Any]:
        """Creates a new playground chat session."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO playground_sessions (id, title, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (session_id, title)
            )
            conn.commit()
        return {"id": session_id, "title": title}

    def list_playground_sessions(self) -> List[Dict[str, Any]]:
        """Lists all playground chat sessions ordered by latest update."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT id, title, created_at, updated_at FROM playground_sessions ORDER BY updated_at DESC")
            return [dict(r) for r in cursor.fetchall()]

    def delete_playground_session(self, session_id: str):
        """Deletes a playground chat session and its messages."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM playground_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM playground_sessions WHERE id = ?", (session_id,))
            conn.commit()

    def add_playground_message(self, session_id: str, role: str, content: str, thinking_process: str = None):
        """Appends a user or assistant message to a session."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO playground_messages (session_id, role, content, thinking_process) VALUES (?, ?, ?, ?)",
                (session_id, role, content, thinking_process)
            )
            conn.execute("UPDATE playground_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
            conn.commit()

    def get_playground_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Fetches all chat messages for a given session ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, session_id, role, content, thinking_process, timestamp FROM playground_messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def log_request(
        self,
        api_key: str,
        endpoint: str,
        status_code: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        ttft_ms: float = 0.0,
        tps: float = 0.0,
        is_error: bool = False,
        prompt_text: str = None,
        completion_text: str = None,
        thinking_text: str = None
    ):
        """Logs a single API request asynchronously/synchronously with connection pooling and payload text."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO api_key_logs 
                    (api_key, endpoint, status_code, prompt_tokens, completion_tokens, ttft_ms, tps, is_error, prompt_text, completion_text, thinking_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        api_key,
                        endpoint,
                        status_code,
                        prompt_tokens,
                        completion_tokens,
                        ttft_ms,
                        tps,
                        1 if is_error else 0,
                        prompt_text,
                        completion_text,
                        thinking_text
                    )
                )
                conn.commit()
        except Exception as e:
            # Fallback safe logging
            print(f"[MetricsDB ERROR] Failed to log metrics: {e}")

    def cleanup_old_logs(self, days: int = 30):
        """Deletes metrics older than specified retention days (FR-005)."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute("DELETE FROM api_key_logs WHERE timestamp < ?", (cutoff,))
            conn.commit()

    def get_aggregated_metrics(self) -> List[Dict[str, Any]]:
        """Returns aggregated SQL metrics per API key for dashboard & Top 5 charts."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    api_key,
                    COUNT(*) as request_count,
                    SUM(is_error) as error_count,
                    SUM(prompt_tokens) as prompt_tokens,
                    SUM(completion_tokens) as completion_tokens,
                    AVG(ttft_ms) as avg_ttft_ms,
                    AVG(tps) as avg_tps,
                    MAX(timestamp) as last_used_at
                FROM api_key_logs
                GROUP BY api_key
                ORDER BY (SUM(prompt_tokens) + SUM(completion_tokens)) DESC
            """)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                p_tok = r["prompt_tokens"] or 0
                c_tok = r["completion_tokens"] or 0
                # FinOps cost estimation: (prompt * 0.0000005) + (completion * 0.0000015)
                est_cost = (p_tok * 0.0000005) + (c_tok * 0.0000015)
                results.append({
                    "api_key": r["api_key"],
                    "request_count": r["request_count"],
                    "error_count": r["error_count"] or 0,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "avg_ttft_ms": round(r["avg_ttft_ms"] or 0.0, 1),
                    "avg_tps": round(r["avg_tps"] or 0.0, 1),
                    "estimated_cost_usd": round(est_cost, 4),
                    "last_used_at": r["last_used_at"] or ""
                })
            return results

    def get_payload_by_id(self, log_id: int) -> Dict[str, Any]:
        """Returns prompt_text, completion_text, and thinking_text for a specific log entry ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, api_key, endpoint, status_code, prompt_tokens, completion_tokens, ttft_ms, tps, prompt_text, completion_text, thinking_text, timestamp FROM api_key_logs WHERE id = ?",
                (log_id,)
            )
            row = cursor.fetchone()
            if not row:
                return {}
            return dict(row)



_metrics_db_instance = None


def get_metrics_db() -> MetricsDB:
    """Returns global singleton MetricsDB instance, initializing on first access."""
    global _metrics_db_instance
    if _metrics_db_instance is None:
        _metrics_db_instance = MetricsDB()
    return _metrics_db_instance


class _LazyMetricsDBProxy:
    """Lazy Proxy for MetricsDB to prevent disk I/O and DB initialization at module import time."""
    def __getattr__(self, name: str):
        return getattr(get_metrics_db(), name)

    def __setattr__(self, name: str, value: Any):
        setattr(get_metrics_db(), name, value)


metrics_db = _LazyMetricsDBProxy()


