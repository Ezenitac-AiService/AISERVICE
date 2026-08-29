#!/usr/bin/env python3
"""Model Gateway 런타임 프로파일 호환 진입점.

구형 `src.core.config`와 별개로, 마이그레이션 프로버가 생성한 하드웨어
프로파일을 런타임에 읽어 VRAM 예산과 fallback 순서를 제공합니다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_MODEL_VRAM_BUDGET_MB = {"llm": 2600, "embedding": 1200, "reranker": 1200}
DEFAULT_FALLBACK_CHAIN = ["vllm", "llama.cpp-cuda", "llama.cpp-cpu-openblas"]
VRAM_SAFETY_LIMIT_MB = int(os.environ.get("VRAM_SAFETY_LIMIT_MB", "5000"))


def _profile_path() -> Path:
    return Path(
        os.environ.get(
            "HARDWARE_PROFILE_PATH",
            Path(__file__).resolve().parent.parent / "config" / "hardware_profile.json",
        )
    )


def get_runtime_profile() -> dict[str, Any]:
    """프로버 산출물을 읽고 누락된 값은 안전한 기본값으로 채웁니다."""
    profile: dict[str, Any] = {}
    path = _profile_path()
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                profile.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    profile.setdefault("vram_safety_limit_mb", VRAM_SAFETY_LIMIT_MB)
    profile.setdefault("model_vram_budget_mb", dict(DEFAULT_MODEL_VRAM_BUDGET_MB))
    profile.setdefault("runtime_fallback_chain", list(DEFAULT_FALLBACK_CHAIN))
    return profile


def get_model_vram_budget() -> dict[str, int]:
    values = get_runtime_profile().get(
        "model_vram_budget_mb", DEFAULT_MODEL_VRAM_BUDGET_MB
    )
    return {key: int(value) for key, value in values.items()}


def get_runtime_fallback_chain() -> list[str]:
    return [
        str(value)
        for value in get_runtime_profile().get(
            "runtime_fallback_chain", DEFAULT_FALLBACK_CHAIN
        )
    ]
