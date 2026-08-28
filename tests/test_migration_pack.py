# -*- coding: utf-8 -*-
"""
tests/test_migration_pack.py
============================
Feature 043: 마이그레이션 팩 v2.0 핵심 유틸리티 및 계약 단위/통합 테스트 스위트.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

from migration_pack.scripts.manifest_utils import (
    calculate_sha256,
    generate_checksums_file,
    verify_checksums_file,
    build_manifest_v2,
    validate_manifest_schema,
)
from migration_pack.scripts.normalize_compose import normalize_compose_content
from model_gateway.scripts.probe_hardware import (
    probe_cpu_features,
    probe_gpu_features,
    generate_build_profile,
)


def test_calculate_sha256_and_checksums_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "sample.txt"
        test_file.write_text("AISERVICE Ubuntu Migration Test Data", encoding="utf-8")

        sha = calculate_sha256(test_file)
        assert len(sha) == 64
        assert isinstance(sha, str)

        cs_path = Path(tmpdir) / "checksums.sha256"
        cs_map = generate_checksums_file([(test_file, "sample.txt")], cs_path)
        assert "sample.txt" in cs_map
        assert cs_map["sample.txt"] == sha

        is_valid, matched, mismatched = verify_checksums_file(cs_path, tmpdir)
        assert is_valid is True
        assert len(matched) == 1
        assert len(mismatched) == 0


def test_manifest_v2_schema_validation():
    source_env = {"os": "Windows 11", "platform": "WSL2", "hostname": "dev-box"}
    target_hw = {
        "cpu": "Intel Core i7-930 (SSE4.2, Non-AVX)",
        "gpu": "NVIDIA GeForce GTX 1070 8GB (Pascal sm_61)",
        "ram_mb": 24576,
        "vram_mb": 8192,
        "llama_cpp_flags": "-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61 -march=native",
        "vram_safety_limit_mb": 5000,
    }
    db_spec = [{
        "name": "pilos_v2",
        "dump_file": "database/pilos_v2.sql.gz",
        "size_bytes": 1024000,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "row_count": 4300000,
    }]
    vol_spec = [{
        "volume_name": "ateam_db_data",
        "archive_file": "volumes/ateam_db_data.tar.gz",
        "size_bytes": 512000,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "is_sparse": True,
    }]
    ddns = {"domain": "ezenitac", "token": "2a6d2828-7400-44fb-a32f-0366a7703b53", "cron_interval_minutes": 5}
    services = ["gateway", "vllm-serv", "redis", "bteam_db", "pilos-db"]
    checksums = {"manifest.json": "abc123"}

    manifest = build_manifest_v2(source_env, target_hw, db_spec, vol_spec, ddns, services, checksums)
    is_valid, errors = validate_manifest_schema(manifest)
    assert is_valid is True, f"Manifest validation failed: {errors}"
    assert manifest["manifest_version"] == "2.0.0"
    assert manifest["zero_config_ready"] is True


def test_normalize_compose_removes_wsl_and_injects_gpu():
    wsl_compose_sample = """
networks:
  aiservice-network:
    name: aiservice-network
volumes:
  bteam_mysql_data:
    external: true
    name: bteam_bteam_mysql_data
services:
  vllm-serv:
    image: vllm-serv:latest
    container_name: vllm-serv-gateway
    volumes:
      - ./model_gateway/models:/app/models
      - /usr/lib/wsl:/usr/lib/wsl:ro
    devices:
      - /dev/dxg:/dev/dxg
    environment:
      - LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers
"""
    normalized = normalize_compose_content(wsl_compose_sample)
    assert "/usr/lib/wsl" not in normalized
    assert "/dev/dxg" not in normalized
    assert "external: true" not in normalized
    assert "deploy:" in normalized
    assert "reservations:" in normalized
    assert "driver: nvidia" in normalized
    assert "capabilities: [gpu]" in normalized


def test_hardware_probe_and_build_profile():
    cpu_nehalem = {
        "model_name": "Intel Core i7-930 @ 2.80GHz",
        "arch": "x86_64",
        "sse4_2": True,
        "avx": False,
        "avx2": False,
        "avx512": False,
        "is_nehalem_legacy": True,
    }
    gpu_gtx1070 = {
        "present": True,
        "name": "NVIDIA GeForce GTX 1070",
        "driver_version": "550.54",
        "compute_capability": "6.1",
        "compute_cap_int": 61,
        "vram_total_mb": 8192,
        "cuda_available": True,
    }

    profile = generate_build_profile(cpu_nehalem, gpu_gtx1070)
    assert profile["recommended_backend"] == "cuda"
    assert "-DGGML_AVX=OFF" in profile["cmake_flags"]
    assert "-DGGML_AVX2=OFF" in profile["cmake_flags"]
    assert "-DCMAKE_CUDA_ARCHITECTURES=61" in profile["cmake_flags"]
    assert profile["vram_safety_limit_mb"] >= 5000
