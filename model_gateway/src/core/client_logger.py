"""
Client Access & Audit Logger Module.
Provides asynchronous non-blocking logging using QueueHandler/QueueListener for HTTP access logs and error logs.
"""

import os
import time
import uuid
import logging
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AccessLogEntry(BaseModel):
    timestamp: str
    client_ip: str
    request_id: str
    method: str
    path: str
    status_code: int
    latency_ms: float
    model: Optional[str] = None
    openai_user: Optional[str] = None
    masked_api_key: Optional[str] = None
    user_agent: Optional[str] = None


class ErrorLogEntry(BaseModel):
    timestamp: str
    request_id: str
    client_ip: str
    path: str
    status_code: int
    exception_type: str
    error_detail: str
    masked_api_key: Optional[str] = None
    traceback_summary: Optional[str] = None


class ClientLoggerManager:
    """Manages asynchronous QueueHandler and RotatingFileHandlers for access and error logs."""

    def __init__(self, log_dir: str = "logs", max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        self.log_dir = log_dir
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        os.makedirs(self.log_dir, exist_ok=True)

        self.access_log_path = os.path.join(self.log_dir, "access.log")
        self.error_log_path = os.path.join(self.log_dir, "error.log")
        self.server_log_path = os.path.join(self.log_dir, "server.log")

        # Create RotatingFileHandlers
        self.access_file_handler = RotatingFileHandler(
            self.access_log_path, maxBytes=self.max_bytes, backupCount=self.backup_count, encoding="utf-8"
        )
        self.access_file_handler.setFormatter(logging.Formatter("%(message)s"))

        self.error_file_handler = RotatingFileHandler(
            self.error_log_path, maxBytes=self.max_bytes, backupCount=self.backup_count, encoding="utf-8"
        )
        self.error_file_handler.setFormatter(logging.Formatter("%(message)s"))

        self.server_file_handler = RotatingFileHandler(
            self.server_log_path, maxBytes=self.max_bytes, backupCount=self.backup_count, encoding="utf-8"
        )
        self.server_file_handler.setFormatter(logging.Formatter("%(message)s"))

        # Setup Queue for Access Logger
        self.access_queue: Queue = Queue()
        self.access_queue_handler = QueueHandler(self.access_queue)
        self.access_logger = logging.getLogger("vllm_serv.access")
        self.access_logger.setLevel(logging.INFO)
        self.access_logger.addHandler(self.access_queue_handler)

        self.access_listener = QueueListener(self.access_queue, self.access_file_handler, self.server_file_handler)
        self.access_listener.start()

        # Setup Queue for Error Logger (writes to error.log and server.log)
        self.error_queue: Queue = Queue()
        self.error_queue_handler = QueueHandler(self.error_queue)
        self.error_logger = logging.getLogger("vllm_serv.error")
        self.error_logger.setLevel(logging.ERROR)
        self.error_logger.addHandler(self.error_queue_handler)

        self.error_listener = QueueListener(self.error_queue, self.error_file_handler, self.server_file_handler)
        self.error_listener.start()

    def log_access(self, entry: AccessLogEntry) -> None:
        parts = [
            f"[{entry.timestamp}]",
            f"[{entry.client_ip}]",
            f"[{entry.request_id}]"
        ]
        if entry.masked_api_key:
            parts.append(f"[key:{entry.masked_api_key}]")
        if entry.openai_user:
            parts.append(f"[user:{entry.openai_user}]")

        parts.append(f"{entry.method} {entry.path} {entry.status_code} - {entry.latency_ms:.1f}ms")

        if entry.model:
            parts.append(f"- model: {entry.model}")

        log_msg = " ".join(parts)
        self.access_logger.info(log_msg)

    def log_error(self, entry: Union[ErrorLogEntry, str]) -> None:
        if isinstance(entry, str):
            timestamp = datetime.now(timezone.utc).isoformat()
            self.error_logger.error(f"[{timestamp}] {entry}")
            return

        parts = [
            f"[{entry.timestamp}]",
            f"[{entry.client_ip}]",
            f"[{entry.request_id}]"
        ]
        if entry.masked_api_key:
            parts.append(f"[key:{entry.masked_api_key}]")

        parts.append(f"{entry.path} {entry.status_code} [{entry.exception_type}]: {entry.error_detail}")
        if entry.traceback_summary:
            parts.append(f"\n  Traceback:\n{entry.traceback_summary}")

        log_msg = " ".join(parts)
        self.error_logger.error(log_msg)



    def get_recent_access_logs(self, limit: int = 50) -> list:
        """Reads recent access log entries from access.log."""
        if not os.path.exists(self.access_log_path):
            return []
        try:
            with open(self.access_log_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            return lines[-limit:]
        except Exception:
            return []

    def stop(self) -> None:
        self.access_listener.stop()
        self.error_listener.stop()




# Global Singleton Manager
_logger_manager: Optional[ClientLoggerManager] = None


def get_client_logger() -> ClientLoggerManager:
    global _logger_manager
    if _logger_manager is None:
        _logger_manager = ClientLoggerManager()
    return _logger_manager
