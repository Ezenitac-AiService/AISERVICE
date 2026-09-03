#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hardware Profile Definition for dev-rtx3060 (SSOT).
Enforces:
- Intel Core i7-4770 (AVX2)
- NVIDIA GeForce RTX 3060 12GB (Compute Capability 8.6, sm_86)
- VRAM Safety Limit: 10240 MB
- Max Concurrent GPU Slots: 4
- Queue Timeout: 60s
- Mock Mode: MOCK_LLAMA_SERVER
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HardwareProfile:
    name: str = "dev-rtx3060"
    cpu: str = "Intel Core i7-4770"
    cpu_features: list[str] = field(default_factory=lambda: ["avx2", "fma"])
    gpu: str = "NVIDIA GeForce RTX 3060 12GB"
    cuda_arch: str = "86"
    total_vram_mb: int = 12288
    vram_safety_limit_mb: int = 10240
    max_gpu_concurrent_slots: int = 4
    queue_timeout_seconds: int = 60
    llama_cpp_n_gpu_layers: int = 99


def is_mock_mode_active() -> bool:
    """Return True if MOCK_LLAMA_SERVER is enabled."""
    return os.environ.get("MOCK_LLAMA_SERVER", "0").lower() in ("1", "true", "yes")


def get_current_profile() -> HardwareProfile:
    """Return the active HardwareProfile based on environment overrides."""
    vram_limit = int(os.environ.get("VRAM_SAFETY_LIMIT_MB", 10240))
    slots = int(os.environ.get("MAX_GPU_CONCURRENT_SLOTS", 4))
    arch = os.environ.get("CUDA_ARCH", "86")

    return HardwareProfile(
        name="dev-rtx3060",
        vram_safety_limit_mb=vram_limit,
        max_gpu_concurrent_slots=slots,
        cuda_arch=arch,
    )


def get_gpu_evidence() -> dict[str, Any]:
    """Generate structured GPU evidence record."""
    prof = get_current_profile()
    mock_mode = is_mock_mode_active()

    return {
        "profile": prof.name,
        "cuda_device": prof.gpu,
        "compute_capability": "8.6",
        "cuda_arch": f"sm_{prof.cuda_arch}",
        "max_concurrent_slots": prof.max_gpu_concurrent_slots,
        "vram_limit_mb": prof.vram_safety_limit_mb,
        "mock_mode": mock_mode,
        "active_acceleration": "CUDA" if not mock_mode else "MOCK_CUDA",
    }
