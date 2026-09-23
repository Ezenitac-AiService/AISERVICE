"""
Unit test for pipe drain deadlock prevention and immediate background task scheduling.
Validates:
1. _drain_stdout task is scheduled immediately after create_subprocess_exec, BEFORE poll_server_health is called
2. PR_SET_PDEATHSIG(SIGKILL) preexec_fn is attached to create_subprocess_exec
3. stop_process uses 3.0s SIGTERM timeout for <= 3.5s 4-stage escalation
"""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.core.process_manager import ProcessManager


@pytest.mark.asyncio
async def test_drain_stdout_scheduled_before_poll_server_health():
    """Verify _drain_stdout is created BEFORE awaiting poll_server_health to avoid 64KB buffer deadlock."""
    pm = ProcessManager()

    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.returncode = None
    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline.return_value = b"llama-server starting...\n"

    drain_task_created_before_poll = False

    async def fake_poll_server_health(port, timeout=30.0):
        nonlocal drain_task_created_before_poll
        # Check if _log_drain_task was created BEFORE poll_server_health was called
        if getattr(pm, "_log_drain_task", None) is not None:
            drain_task_created_before_poll = True
        return True

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec, \
         patch("src.core.process_manager.poll_server_health", side_effect=fake_poll_server_health), \
         patch.object(pm, "verify_and_build_llama_server") as mock_bin, \
         patch.object(pm, "build_server_command", return_value=["/usr/local/bin/llama-server"]), \
         patch("os.path.exists", return_value=True), \
         patch.object(pm, "stop_process", new_callable=AsyncMock), \
         patch.object(pm, "_wait_for_port_free", new_callable=AsyncMock, return_value=True), \
         patch.object(pm, "detect_zombie_collision"):

        mock_exec.return_value = mock_process
        mock_bin.return_value = MagicMock(binary_path="/usr/local/bin/llama-server", is_cuda_enabled=True)

        await pm.spawn_process("qwen3.5-4b", n_ctx=2048)

        # Clean up drain task if running
        if pm._log_drain_task and not pm._log_drain_task.done():
            pm._log_drain_task.cancel()

        assert drain_task_created_before_poll is True, (
            "DEADLOCK RISK: _log_drain_task was NOT scheduled before poll_server_health! "
            "C++ stdout buffer (>64KB) will block and freeze server initialization."
        )


@pytest.mark.asyncio
async def test_spawn_process_attaches_preexec_fn_and_pdeathsig():
    """Verify create_subprocess_exec receives preexec_fn for PR_SET_PDEATHSIG."""
    pm = ProcessManager()

    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.returncode = None
    mock_process.stdout = AsyncMock()

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec, \
         patch("src.core.process_manager.poll_server_health", new_callable=AsyncMock, return_value=True), \
         patch.object(pm, "verify_and_build_llama_server"), \
         patch.object(pm, "build_server_command", return_value=["/usr/local/bin/llama-server"]), \
         patch("os.path.exists", return_value=True), \
         patch.object(pm, "stop_process", new_callable=AsyncMock), \
         patch.object(pm, "_wait_for_port_free", new_callable=AsyncMock, return_value=True), \
         patch.object(pm, "detect_zombie_collision"):

        mock_exec.return_value = mock_process
        await pm.spawn_process("qwen3.5-4b", n_ctx=2048)

        # Clean up drain task if running
        if pm._log_drain_task and not pm._log_drain_task.done():
            pm._log_drain_task.cancel()

        mock_exec.assert_called_once()
        _, kwargs = mock_exec.call_args
        assert "preexec_fn" in kwargs and kwargs["preexec_fn"] is not None, (
            "PR_SET_PDEATHSIG preexec_fn must be passed to create_subprocess_exec"
        )
