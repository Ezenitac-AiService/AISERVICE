import os
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from src.core.process_manager import ProcessManager

@pytest.mark.asyncio
async def test_drain_stdout_flushes_to_log_file(tmp_path):
    base_dir = str(tmp_path)
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    bench_log = os.path.join(logs_dir, "benchmark.log")
    err_log = os.path.join(logs_dir, "error.log")

    pm = ProcessManager(port=8081)
    
    # Mock asyncio StreamReader
    stream = asyncio.StreamReader()
    stream.feed_data(b"llama_server_init: loaded model\n")
    stream.feed_data(b"llama_kv_cache_init: kv cache allocated\n")
    stream.feed_eof()

    with patch.object(pm, "_get_log_paths", return_value=(bench_log, err_log)):
        await pm._drain_stdout(stream)

    assert os.path.exists(bench_log)
    with open(bench_log, "r", encoding="utf-8") as f:
        content = f.read()
        assert "loaded model" in content
        assert "kv cache allocated" in content

@pytest.mark.asyncio
async def test_drain_stdout_captures_exit_137_kernel_oom(tmp_path):
    base_dir = str(tmp_path)
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    bench_log = os.path.join(logs_dir, "benchmark.log")
    err_log = os.path.join(logs_dir, "error.log")

    from src.core.process_manager import ProcessState, ProcessStatusEnum
    pm = ProcessManager(port=8081)
    pm.state = ProcessState(status=ProcessStatusEnum.LOADING, port=8081)
    mock_process = AsyncMock()
    mock_process.wait.return_value = 0
    mock_process.returncode = 137
    mock_process.pid = 9999
    pm.process = mock_process

    stream = asyncio.StreamReader()
    stream.feed_data(b"CUDA OOM error allocating buffer\n")
    stream.feed_eof()

    with patch.object(pm, "_get_log_paths", return_value=(bench_log, err_log)):
        await pm._drain_stdout(stream)

    assert os.path.exists(err_log)
    with open(err_log, "r", encoding="utf-8") as f:
        err_content = f.read()
        assert "KERNEL_OOM_KILLER_EXIT_137" in err_content

@pytest.mark.asyncio
async def test_benchmark_log_rotation(tmp_path):
    base_dir = str(tmp_path)
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    bench_log = os.path.join(logs_dir, "benchmark.log")
    old_log = os.path.join(logs_dir, "benchmark.log.old")
    err_log = os.path.join(logs_dir, "error.log")

    # Create dummy 11MB benchmark.log file
    with open(bench_log, "wb") as f:
        f.write(b"X" * (11 * 1024 * 1024))

    pm = ProcessManager(port=8081)
    stream = asyncio.StreamReader()
    stream.feed_data(b"new log line after rotation\n")
    stream.feed_eof()

    with patch.object(pm, "_get_log_paths", return_value=(bench_log, err_log)):
        await pm._drain_stdout(stream)

    assert os.path.exists(old_log)
    assert os.path.exists(bench_log)
    with open(bench_log, "r", encoding="utf-8") as f:
        content = f.read()
        assert "new log line after rotation" in content
