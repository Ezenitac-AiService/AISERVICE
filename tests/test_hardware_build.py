# -*- coding: utf-8 -*-
"""
tests/test_hardware_build.py
============================
User Story 2: 하드웨어 적응 및 llama.cpp JIT 빌드 스크립트 테스트.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from model_gateway.scripts.probe_hardware import generate_build_profile


def test_i7_930_non_avx_flags():
    cpu = {
        "model_name": "Intel(R) Core(TM) i7-930 @ 2.80GHz",
        "arch": "x86_64",
        "sse4_2": True,
        "avx": False,
        "avx2": False,
        "avx512": False,
        "is_nehalem_legacy": True,
    }
    gpu = {
        "present": True,
        "name": "NVIDIA GeForce GTX 1070",
        "compute_capability": "6.1",
        "compute_cap_int": 61,
        "vram_total_mb": 8192,
        "cuda_available": True,
    }
    profile = generate_build_profile(cpu, gpu)

    assert "-DGGML_AVX=OFF" in profile["cmake_flags"]
    assert "-DGGML_AVX2=OFF" in profile["cmake_flags"]
    assert "-DCMAKE_CUDA_ARCHITECTURES=61" in profile["cmake_flags"]
    assert "-DGGML_CUDA=ON" in profile["cmake_flags"]
    assert profile["vram_safety_limit_mb"] >= 5000


def test_build_llama_script_exists():
    script_path = ROOT_DIR / "model_gateway" / "scripts" / "build_llama.sh"
    assert script_path.is_file()
    content = script_path.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in content
    assert "probe_hardware.py" in content
    assert "cmake" in content
