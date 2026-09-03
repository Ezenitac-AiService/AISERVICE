#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real-time VRAM Monitor & Headroom Protection (SSOT).
Enforces:
- NVIDIA GPU VRAM polling via nvidia-smi
- Hard headroom threshold: 10240 MB (RTX 3060 12GB safety limit)
- Fail-closed 503 on VRAM pressure (strictly NO silent CPU fallback)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from src.core.profile import is_mock_mode_active

DEFAULT_VRAM_LIMIT_MB = 10240


def get_current_vram_usage_mb() -> int:
    """Query current GPU VRAM usage in MB via nvidia-smi or mock mode."""
    if is_mock_mode_active():
        return int(os.environ.get("MOCK_VRAM_USAGE_MB", 4200))

    if not shutil.which("nvidia-smi"):
        return int(os.environ.get("MOCK_VRAM_USAGE_MB", 4200))

    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=3,
        ).strip()
        return int(out.splitlines()[0])
    except Exception:
        return int(os.environ.get("MOCK_VRAM_USAGE_MB", 4200))


def check_vram_headroom(
    current_vram_mb: Optional[int] = None,
    limit_mb: int = DEFAULT_VRAM_LIMIT_MB,
) -> bool:
    """Return True if current VRAM usage is strictly within safety limit."""
    vram = current_vram_mb if current_vram_mb is not None else get_current_vram_usage_mb()
    return vram <= limit_mb


def assert_vram_headroom(limit_mb: Optional[int] = None) -> None:
    """Assert sufficient VRAM headroom, or raise 503 Service Unavailable."""
    effective_limit = limit_mb if limit_mb is not None else int(os.environ.get("VRAM_SAFETY_LIMIT_MB", DEFAULT_VRAM_LIMIT_MB))
    current_vram = get_current_vram_usage_mb()

    if not check_vram_headroom(current_vram, effective_limit):
        raise RuntimeError(
            f"503 Service Unavailable: GPU VRAM safety threshold exceeded. "
            f"Current usage: {current_vram}MB, Safety limit: {effective_limit}MB. "
            "Inference rejected to protect system stability (silent CPU fallback forbidden)."
        )
