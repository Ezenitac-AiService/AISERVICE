"""
Unit tests for ProcessManager cleanup and port readiness (T011, T012 / US2).
"""

import pytest
from unittest.mock import patch, MagicMock
from src.core.process_manager import ProcessManager


def test_force_kill_zombie_llama_servers_pinpoint_cleanup(monkeypatch):
    """T011/US2: force_kill_zombie_llama_servers targets backend ports with fuser and pgrep llama_cpp.server."""
    called_cmds = []

    def mock_run(cmd, capture_output=True, check=False):
        called_cmds.append(cmd)

    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("subprocess.check_output", lambda cmd, text=True, timeout=2: "")

    ProcessManager.force_kill_zombie_llama_servers(target_ports=(8081, 8089, 8090, 8091))

    assert len(called_cmds) == 4
    assert called_cmds[0] == ["fuser", "-k", "-9", "8081/tcp"]
    assert called_cmds[1] == ["fuser", "-k", "-9", "8089/tcp"]
    assert called_cmds[2] == ["fuser", "-k", "-9", "8090/tcp"]
    assert called_cmds[3] == ["fuser", "-k", "-9", "8091/tcp"]


@pytest.mark.asyncio
async def test_wait_for_port_free_readiness_check():
    """T012/US2: _wait_for_port_free requires continuous non-zero verification."""
    pm = ProcessManager(port=8081)
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        # Returns 1 (free) twice in a row
        mock_sock.connect_ex.return_value = 1
        mock_sock_cls.return_value.__enter__.return_value = mock_sock

        is_free = await pm._wait_for_port_free(max_retries=3, interval=0.01)
        assert is_free is True
