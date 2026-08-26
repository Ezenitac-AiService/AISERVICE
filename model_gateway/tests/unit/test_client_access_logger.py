"""
Unit tests for ClientAccessLogMiddleware and ClientLoggerManager.
"""

import os
import tempfile
import pytest
from src.core.client_logger import ClientLoggerManager, AccessLogEntry, ErrorLogEntry


def test_client_logger_manager_access_and_error(tmp_path):
    log_dir = str(tmp_path / "logs")
    logger_mgr = ClientLoggerManager(log_dir=log_dir, max_bytes=1024 * 1024, backup_count=2)

    access_entry = AccessLogEntry(
        timestamp="2026-07-30T05:30:00Z",
        client_ip="192.168.1.100",
        request_id="req-12345",
        method="POST",
        path="/v1/chat/completions",
        status_code=200,
        latency_ms=125.5,
        model="qwen3.5-4b",
        openai_user="user-test-1",
        masked_api_key="sk-***key1",
        user_agent="pytest-client"
    )

    logger_mgr.log_access(access_entry)

    error_entry = ErrorLogEntry(
        timestamp="2026-07-30T05:30:01Z",
        request_id="req-12345",
        client_ip="192.168.1.100",
        path="/v1/chat/completions",
        status_code=400,
        exception_type="HTTPException",
        error_detail="Invalid request body",
        masked_api_key="sk-***key1"
    )

    logger_mgr.log_error(error_entry)

    # Stop listeners to flush logs to disk
    logger_mgr.stop()

    access_log_file = os.path.join(log_dir, "access.log")
    error_log_file = os.path.join(log_dir, "error.log")

    assert os.path.exists(access_log_file)
    assert os.path.exists(error_log_file)

    with open(access_log_file, "r", encoding="utf-8") as f:
        access_content = f.read()
        assert "192.168.1.100" in access_content
        assert "req-12345" in access_content
        assert "POST /v1/chat/completions 200 - 125.5ms" in access_content
        assert "model: qwen3.5-4b" in access_content
        assert "sk-***key1" in access_content


    with open(error_log_file, "r", encoding="utf-8") as f:
        error_content = f.read()
        assert "192.168.1.100" in error_content
        assert "HTTPException" in error_content
        assert "Invalid request body" in error_content


def test_rotating_file_handler_config(tmp_path):
    log_dir = str(tmp_path / "logs_rotation")
    logger_mgr = ClientLoggerManager(log_dir=log_dir, max_bytes=10 * 1024 * 1024, backup_count=5)

    assert logger_mgr.access_file_handler.maxBytes == 10 * 1024 * 1024
    assert logger_mgr.access_file_handler.backupCount == 5
    assert logger_mgr.error_file_handler.maxBytes == 10 * 1024 * 1024
    assert logger_mgr.error_file_handler.backupCount == 5

    logger_mgr.stop()
