import os
import tempfile
import pytest
from unittest.mock import MagicMock

from src.api.middleware.client_access_logger import ClientAccessLogMiddleware
import src.core.client_logger as client_logger_mod

@pytest.mark.asyncio
async def test_error_traceback_logging_format():
    """T004/FR-001: Verifies multi-line traceback logging format in error.log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = client_logger_mod.ClientLoggerManager(log_dir=tmpdir)
        client_logger_mod._logger_manager = mgr
        
        middleware = ClientAccessLogMiddleware(app=MagicMock())
        
        try:
            raise ValueError("Test internal backend exception for traceback verification")
        except Exception as exc:
            middleware.log_error(
                client_ip="127.0.0.1",
                request_id="req-test-traceback",
                endpoint="/v1/chat/completions",
                status_code=503,
                detail="Service Unavailable due to backend failure",
                exc=exc
            )
            
        mgr.stop()
        
        error_log_path = os.path.join(tmpdir, "error.log")
        assert os.path.exists(error_log_path)
        with open(error_log_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        assert "503 [ValueError]" in content
        assert "req-test-traceback" in content
        assert "Service Unavailable due to backend failure" in content
        assert "Traceback (most recent call last):" in content
