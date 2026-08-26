import os
import shutil
import pytest
from unittest.mock import patch, MagicMock

from src.core.process_manager import ProcessManager, LlamaServerBinaryInfo


def test_real_system_native_binary_detection():
    """Real system test verifying ProcessManager excludes Ollama internal library paths."""
    info = ProcessManager.verify_and_build_llama_server()
    assert isinstance(info, LlamaServerBinaryInfo)
    assert "ollama" not in info.binary_path.lower()
    assert info.build_source != "OLLAMA_LIB"


def test_binary_path_ollama_path_exclusion():
    """Unit test verifying /usr/local/lib/ollama/llama-server is strictly excluded."""
    def custom_exists(path):
        if path in ("/usr/local/lib/ollama/llama-server", "/opt/ollama/lib/ollama/llama-server"):
            return True
        return False

    def custom_access(path, mode):
        if path in ("/usr/local/lib/ollama/llama-server", "/opt/ollama/lib/ollama/llama-server"):
            return True
        return False

    with patch("shutil.which", return_value=None), \
         patch("os.path.exists", side_effect=custom_exists), \
         patch("os.access", side_effect=custom_access):
        info = ProcessManager.verify_and_build_llama_server()
        assert "ollama" not in info.binary_path.lower()
        assert info.build_source != "OLLAMA_LIB"


def test_binary_executable_sanity_check():
    """Unit test verifying _is_binary_executable_sanity returns False for Ollama paths."""
    assert ProcessManager._is_binary_executable_sanity("/usr/local/lib/ollama/llama-server") is False
    assert ProcessManager._is_binary_executable_sanity("") is False
    assert ProcessManager._is_binary_executable_sanity("/invalid/non_existent_path") is False


def test_binary_path_priority_shutil_which():
    """Unit test verifying shutil.which finding standalone valid llama-server takes priority."""
    with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/llama-server" if cmd == "llama-server" else None), \
         patch.object(ProcessManager, "_is_binary_executable_sanity", return_value=True):
        info = ProcessManager.verify_and_build_llama_server()
        assert info.binary_path == "/usr/bin/llama-server"
        assert info.build_source == "PATH"

