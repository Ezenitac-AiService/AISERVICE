"""
Unit tests for ProcessManager C++ llama-server binary discovery and validation.
Validates:
1. LlamaServerBinaryInfo data model integrity
2. /usr/local/bin/llama-server SSOT priority over other paths
3. _is_binary_executable_sanity 5.0-second timeout
4. FileNotFoundError raised when binary is missing (zero legacy Python fallback)
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from src.core.process_manager import ProcessManager, LlamaServerBinaryInfo


def test_llama_server_binary_info_model():
    """Verify LlamaServerBinaryInfo schema and immutability."""
    info = LlamaServerBinaryInfo(
        binary_path="/usr/local/bin/llama-server",
        is_cuda_enabled=True,
        build_source="SYSTEM_BIN"
    )
    assert info.binary_path == "/usr/local/bin/llama-server"
    assert info.is_cuda_enabled is True
    assert info.build_source == "SYSTEM_BIN"
    with pytest.raises(Exception):
        info.binary_path = "/usr/bin/llama-server"


def test_sanity_timeout_is_at_least_5_seconds():
    """Verify _is_binary_executable_sanity uses timeout >= 5.0s."""
    with patch("os.path.exists", return_value=True), \
         patch("os.access", return_value=True), \
         patch("subprocess.run") as mock_subproc:
        mock_subproc.return_value = MagicMock(returncode=0)

        result = ProcessManager._is_binary_executable_sanity("/usr/local/bin/llama-server")
        assert result is True
        mock_subproc.assert_called_once()
        _, kwargs = mock_subproc.call_args
        assert kwargs.get("timeout") is not None
        assert kwargs["timeout"] >= 5.0, f"Expected timeout >= 5.0s, got {kwargs.get('timeout')}"


def test_ssot_binary_path_priority():
    """Verify /usr/local/bin/llama-server is checked first as SSOT."""
    with patch.object(ProcessManager, "_is_binary_executable_sanity") as mock_sanity:
        # Simulate /usr/local/bin/llama-server is valid
        mock_sanity.side_effect = lambda path: path == "/usr/local/bin/llama-server"

        info = ProcessManager.verify_and_build_llama_server()
        assert info.binary_path == "/usr/local/bin/llama-server"
        assert info.build_source in ("SYSTEM_BIN", "SSOT_BIN", "ENV_BIN")
        assert info.is_cuda_enabled is True


def test_missing_binary_raises_file_not_found():
    """Verify FileNotFoundError is raised when no C++ llama-server binary is found (no Python fallback)."""
    with patch.object(ProcessManager, "_is_binary_executable_sanity", return_value=False), \
         patch("shutil.which", return_value=None), \
         patch("os.path.exists", return_value=False):
        with pytest.raises(FileNotFoundError) as exc_info:
            ProcessManager.verify_and_build_llama_server()
        assert "llama-server" in str(exc_info.value).lower()
