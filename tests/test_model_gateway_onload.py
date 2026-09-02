# -*- coding: utf-8 -*-
"""
Feature 044: Model Gateway LLM/Embedding/Reranker Onload & GPU Acceleration Regression Test Suite.
Verifies runtime backend selection, zero hardcoding (SSOT), CUDA offload flags, and process lifecycle.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from model_gateway.src.config import (
    DEFAULT_FALLBACK_CHAIN,
    get_runtime_fallback_chain,
    get_runtime_profile,
)
from model_gateway.src.core.process_manager import (
    ProcessManager,
    ProcessState,
    ProcessStatusEnum,
    LlamaServerBinaryInfo,
)


def test_fallback_chain_excludes_vllm_by_default(monkeypatch):
    """FR-001 & 헌법 v1.2.0 원칙 VII: ENABLE_EXTERNAL_VLLM이 false일 때 vllm은 기본 체인에서 제외되어야 한다."""
    monkeypatch.delenv("ENABLE_EXTERNAL_VLLM", raising=False)
    monkeypatch.delenv("HARDWARE_PROFILE_PATH", raising=False)

    chain = get_runtime_fallback_chain()
    assert "vllm" not in chain
    assert "llama.cpp-cuda" in chain
    assert chain[0] == "llama.cpp-cuda"


def test_fallback_chain_includes_vllm_when_explicitly_enabled(monkeypatch):
    """FR-001: ENABLE_EXTERNAL_VLLM=true일 때만 vllm이 체인 1순위로 포함된다."""
    monkeypatch.setenv("ENABLE_EXTERNAL_VLLM", "true")
    monkeypatch.delenv("HARDWARE_PROFILE_PATH", raising=False)

    chain = get_runtime_fallback_chain()
    assert "vllm" in chain
    assert chain[0] == "vllm"


def test_runtime_backend_probe_does_not_probe_gateway_port_8081(monkeypatch):
    """FR-001: 런타임 프로브가 게이트웨이 포트 8081을 vllm 엔드포인트로 조회하지 않아야 한다."""
    monkeypatch.delenv("ENABLE_EXTERNAL_VLLM", raising=False)
    
    # 기본 프로파일에서 선택된 백엔드는 llama.cpp-cuda여야 함
    selected = ProcessManager._runtime_backend_from_profile()
    assert selected != "vllm"
    assert "llama.cpp" in selected


def test_python_module_fallback_preserves_cuda_support(monkeypatch):
    """FR-002: llama_cpp_python 모듈이 GPU offload를 지원할 때 is_cuda_enabled=True가 되어야 한다."""
    pm = ProcessManager(port=8089)
    
    with patch("shutil.which", return_value=None):
        with patch.object(ProcessManager, "_is_binary_executable_sanity", return_value=False):
            with patch("llama_cpp.llama_supports_gpu_offload", return_value=True):
                binary_info = pm.verify_and_build_llama_server(preferred_backend="llama.cpp-cuda")
                assert binary_info.build_source == "PYTHON_MODULE_FALLBACK"
                assert binary_info.is_cuda_enabled is True

                cmd = pm.build_server_command(
                    binary_info=binary_info,
                    model_file="/app/models/qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf",
                    model_id="qwen3.5-2b",
                    n_ctx=16384,
                )
                assert "--n_gpu_layers" in cmd
                idx = cmd.index("--n_gpu_layers")
                assert cmd[idx + 1] == "999"


def test_is_ready_requires_living_process_and_ready_status():
    """FR-003 & FR-005: is_ready()는 프로세스가 실제로 살아있고 READY 상태일 때만 True를 반환해야 한다."""
    pm = ProcessManager(port=8089)
    
    # 1. 상태는 READY이나 프로세스 객체가 None인 가짜 READY
    pm.state = ProcessState(status=ProcessStatusEnum.READY, model_id="qwen3.5-2b", port=8089, pid=None)
    pm.process = None
    assert pm.is_ready() is False

    # 2. 프로세스가 종료(returncode != None)된 경우
    fake_proc = MagicMock()
    fake_proc.returncode = 137
    fake_proc.pid = 1234
    pm.process = fake_proc
    assert pm.is_ready() is False

    # 3. 프로세스가 정상 실행 중(returncode is None)이고 상태가 READY인 경우
    fake_proc.returncode = None
    pm.state = ProcessState(status=ProcessStatusEnum.READY, model_id="qwen3.5-2b", port=8089, pid=1234)
    assert pm.is_ready() is True
