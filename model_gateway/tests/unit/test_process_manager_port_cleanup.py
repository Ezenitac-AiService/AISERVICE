import os
import pytest
from src.core.process_manager import ProcessManager

def test_process_manager_cleanup_zombie_on_port():
    """T005/FR-002: Verifies _cleanup_zombie_on_port method exists and runs without crashing."""
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    pm = ProcessManager(port=8089)
    # Call cleanup helper for mock test
    pm._cleanup_zombie_on_port(8089)
    assert pm.port == 8089
