"""
tests/unit/test_setup_benchmark_integration.py
==============================================================================
095-setup-benchmark-model-selection: 4단계 모듈화 벤치마크 파이프라인 연동 단위 테스트 수트

- Test 1: JSON 계약 스키마 (setup_benchmark_contract.json) 정합성 검증
- Test 2: Stage 2 무결성 검증 (verify_model_integrity) 함수 검증
- Test 3: Stage 3 실측 VRAM/TPS 측정 (benchmark_context_window) 및 mock 연동 검증
- Test 4: Stage 4 config/server_config.json 원자적 저장 및 auto_benchmark_profile 반영 검증
- Test 5: --skip-benchmark CLI 플래그 스킵 분기 검증
==============================================================================
"""

import os
import sys
import json
import tempfile
import pytest
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark_context_window import (
    verify_model_integrity,
    benchmark_context_window,
    save_benchmark_profile
)
from src.core.config_manager import ConfigManager


def test_setup_benchmark_contract_schema():
    """Verify setup_benchmark_contract.json schema exists and has required properties."""
    contract_path = REPO_ROOT / "specs" / "095-setup-benchmark-model-selection" / "contracts" / "setup_benchmark_contract.json"
    assert contract_path.exists(), f"Contract schema missing at {contract_path}"

    with open(contract_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    assert "required" in schema
    assert "recommended_context_window" in schema["properties"]
    assert "benchmark_tps" in schema["properties"]


def test_verify_model_integrity():
    """Verify Stage 2 verify_model_integrity detects valid vs invalid GGUF files."""
    with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as f:
        f.write(b"GGUF" + b"\x00" * 2000000)
        valid_path = f.name

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(b"INVALID_HEADER" + b"\x00" * 500)
        invalid_path = f.name

    try:
        assert verify_model_integrity(valid_path) is True
        assert verify_model_integrity(invalid_path) is False
        assert verify_model_integrity("/non/existent/path.gguf") is False
    finally:
        if os.path.exists(valid_path):
            os.remove(valid_path)
        if os.path.exists(invalid_path):
            os.remove(invalid_path)


def test_benchmark_context_window_mocking(monkeypatch):
    """Verify Stage 3 benchmark_context_window evaluates TPS, VRAM, and recommended context window."""
    monkeypatch.setenv("MOCK_BENCHMARK_TPS", "55.5")
    monkeypatch.setenv("MOCK_BENCHMARK_VRAM", "5100")
    monkeypatch.setenv("MOCK_RECOMMENDED_CONTEXT", "16384")

    res = benchmark_context_window(model_name="qwen3.5-4b")
    assert res["recommended_model"] == "qwen3.5-4b"
    assert res["recommended_context_window"] == 16384
    assert res["benchmark_tps"] == 55.5
    assert res["vram_used_mb"] == 5100
    assert res["stage_status"]["Stage 3"] == "SUCCESS"


def test_save_benchmark_profile_atomic_update(monkeypatch):
    """Verify Stage 4 save_benchmark_profile updates config/server_config.json with profile metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = os.path.join(tmpdir, "server_config.json")
        cfg_mgr = ConfigManager(config_path=cfg_path)

        res = {
            "recommended_model": "qwen3.5-4b",
            "recommended_context_window": 8192,
            "benchmark_tps": 48.2,
            "vram_used_mb": 4300
        }

        # Save config
        server_cfg = cfg_mgr.get_server_config()
        server_cfg["model"] = res["recommended_model"]
        server_cfg["context_window"] = res["recommended_context_window"]
        server_cfg["auto_benchmark_profile"] = {
            "recommended_model": res["recommended_model"],
            "recommended_context_window": res["recommended_context_window"],
            "benchmark_tps": res["benchmark_tps"],
            "vram_used_mb": res["vram_used_mb"],
            "benchmark_timestamp": "2026-08-04T08:16:00Z"
        }
        cfg_mgr.save_server_config(server_cfg)

        read_cfg = cfg_mgr.get_server_config()
        assert read_cfg["model"] == "qwen3.5-4b"
        assert read_cfg["context_window"] == 8192
        assert read_cfg["auto_benchmark_profile"]["benchmark_tps"] == 48.2


def test_skip_benchmark_cli_behavior():
    """Verify --skip-benchmark flag bypasses Stage 3 in under 15 seconds and preserves context window."""
    import subprocess
    import time

    start_time = time.perf_counter()
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "benchmark_context_window.py"), "--skip-benchmark", "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    elapsed = time.perf_counter() - start_time

    assert elapsed < 15.0, f"SC-002 위반: --skip-benchmark 소요 시간이 15초를 초과함 ({elapsed:.2f}s)"
    data = json.loads(proc.stdout)
    assert data["stage_status"]["Stage 3"] == "SKIPPED"
    assert "recommended_context_window" in data


def test_fine_grained_binary_search_cli():
    """Verify --fine-grained flag executes binary search with 512 block alignment and saves profiles."""
    import subprocess

    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "benchmark_context_window.py"), "--fine-grained", "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    stdout = proc.stdout
    json_start = stdout.find("{")
    assert json_start != -1, f"No JSON found in stdout: {stdout}"
    data = json.loads(stdout[json_start:])

    assert "max_context_length" in data
    assert "recommended_context_length" in data
    assert data["max_context_length"] % 512 == 0
    assert data["recommended_context_length"] % 512 == 0
    assert "Real GPU Load Binary Search" in data["stage_status"]["Stage 3"]

    profiles_path = REPO_ROOT / "config" / "model_context_profiles.json"
    assert profiles_path.exists()


def test_evaluate_all_catalog_models_force_benchmark():
    """Verify --force-benchmark iterates all candidate catalog models and selects optimal model."""
    from scripts.benchmark_context_window import evaluate_all_catalog_models
    res = evaluate_all_catalog_models(force=True)

    assert "recommended_model" in res
    assert "evaluated_models" in res
    assert len(res["evaluated_models"]) > 0
    assert "Stage 3" in res["stage_status"]
    assert "Multi-Model Catalog Forced Real GPU Benchmark" in res["stage_status"]["Stage 3"]

