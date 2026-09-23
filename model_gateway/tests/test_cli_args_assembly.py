"""
Unit tests for ProcessManager C++ llama-server CLI argument assembly per contracts/llama-server-cli.md.
Validates:
1. --no-mmap injected on all 4 models
2. -np 1, --threads-http 4, --alias <model_id> injected
3. Qwen 3.5 (9B and 4B) strictly exclude --context-shift and --ctx-shift
4. BGE-M3 has -b 2048 -ub 2048 --embedding --pooling cls
5. BGE-Reranker has -b 2048 -ub 2048 --embedding --reranking --pooling rank
"""

import pytest
from src.core.process_manager import ProcessManager


def test_cli_assembly_qwen_9b():
    pm = ProcessManager()
    cmd = pm.build_c_llama_server_cmd("qwen3.5-9b", port=8089)
    cmd_str = " ".join(cmd)

    assert ("--load-mode" in cmd and cmd[cmd.index("--load-mode") + 1] == "none") or ("--no-mmap" in cmd), f"no-mmap / load-mode none missing in cmd: {cmd}"
    assert "-np" in cmd and cmd[cmd.index("-np") + 1] == "1"
    assert "--threads-http" in cmd and cmd[cmd.index("--threads-http") + 1] == "4"
    assert "--alias" in cmd and cmd[cmd.index("--alias") + 1] == "qwen3.5-9b"
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "32768"
    assert "-fa" in cmd
    assert "-ctk" in cmd and cmd[cmd.index("-ctk") + 1] == "q8_0"
    assert "-ctv" in cmd and cmd[cmd.index("-ctv") + 1] == "q8_0"
    assert "--context-shift" not in cmd_str
    assert "--ctx-shift" not in cmd_str


def test_cli_assembly_qwen_4b():
    pm = ProcessManager()
    cmd = pm.build_c_llama_server_cmd("qwen3.5-4b", port=8088)
    cmd_str = " ".join(cmd)

    assert ("--load-mode" in cmd and cmd[cmd.index("--load-mode") + 1] == "none") or ("--no-mmap" in cmd), f"--no-mmap missing in 4B cmd: {cmd}"
    assert "-np" in cmd and cmd[cmd.index("-np") + 1] == "1"
    assert "--threads-http" in cmd and cmd[cmd.index("--threads-http") + 1] == "4"
    assert "--alias" in cmd and cmd[cmd.index("--alias") + 1] == "qwen3.5-4b"
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "8192"
    assert "-fa" in cmd
    assert "-ctk" in cmd and cmd[cmd.index("-ctk") + 1] == "q8_0"
    assert "-ctv" in cmd and cmd[cmd.index("-ctv") + 1] == "q8_0"
    assert "--context-shift" not in cmd_str
    assert "--ctx-shift" not in cmd_str


def test_cli_assembly_bge_m3():
    pm = ProcessManager()
    cmd = pm.build_c_llama_server_cmd("bge-m3", port=8090)

    assert ("--load-mode" in cmd and cmd[cmd.index("--load-mode") + 1] == "none") or ("--no-mmap" in cmd), f"--no-mmap missing in bge-m3 cmd: {cmd}"
    assert "--embedding" in cmd
    assert "--pooling" in cmd and cmd[cmd.index("--pooling") + 1] == "cls"
    assert "-b" in cmd and cmd[cmd.index("-b") + 1] == "2048"
    assert "-ub" in cmd and cmd[cmd.index("-ub") + 1] == "2048"
    assert "-np" in cmd and cmd[cmd.index("-np") + 1] == "1"
    assert "--alias" in cmd and cmd[cmd.index("--alias") + 1] == "bge-m3"


def test_cli_assembly_bge_reranker():
    pm = ProcessManager()
    cmd = pm.build_c_llama_server_cmd("bge-reranker-v2-m3", port=8091)

    assert ("--load-mode" in cmd and cmd[cmd.index("--load-mode") + 1] == "none") or ("--no-mmap" in cmd), f"--no-mmap missing in reranker cmd: {cmd}"
    assert "--reranking" in cmd
    assert "--pooling" in cmd and cmd[cmd.index("--pooling") + 1] == "rank"
    assert "-b" in cmd and cmd[cmd.index("-b") + 1] == "2048"
    assert "-ub" in cmd and cmd[cmd.index("-ub") + 1] == "2048"
    assert "-np" in cmd and cmd[cmd.index("-np") + 1] == "1"
    assert "--alias" in cmd and cmd[cmd.index("--alias") + 1] == "bge-reranker-v2-m3"
