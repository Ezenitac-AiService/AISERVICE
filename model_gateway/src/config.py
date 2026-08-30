#!/usr/bin/env python3
"""Model Gateway 런타임 프로파일 호환 진입점.

구형 `src.core.config`와 별개로, 마이그레이션 프로버가 생성한 하드웨어
프로파일을 런타임에 읽어 VRAM 예산과 fallback 순서를 제공합니다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

DEFAULT_MODEL_VRAM_BUDGET_MB = {"llm": 2600, "embedding": 1200, "reranker": 1200}
DEFAULT_FALLBACK_CHAIN = ["vllm", "llama.cpp-cuda", "llama.cpp-cpu-openblas"]
RUNTIME_COMPATIBILITY_ERROR_MARKERS = (
    "illegal instruction",
    "cuda error",
    "cuda mismatch",
    "no kernel image",
    "out of memory",
    "oom",
)
def clamp_vram_safety_limit(value: Any) -> int:
    """모든 입력 경로에서 VRAM safety limit을 0..5,000MB로 제한합니다."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 5000
    return max(0, min(parsed, 5000))


VRAM_SAFETY_LIMIT_MB = clamp_vram_safety_limit(
    os.environ.get("VRAM_SAFETY_LIMIT_MB", "5000")
)


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
    profile["vram_safety_limit_mb"] = clamp_vram_safety_limit(
        profile.get("vram_safety_limit_mb", VRAM_SAFETY_LIMIT_MB)
    )
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


def is_runtime_compatibility_error(message: object) -> bool:
    """런타임 출력에서 CPU/CUDA 호환성 fallback이 필요한 오류를 판정합니다."""
    text = str(message).lower()
    return any(marker in text for marker in RUNTIME_COMPATIBILITY_ERROR_MARKERS)


def attempt_runtime_backends(probe) -> tuple[str, list[str]]:
    """fallback 순서대로 실제 probe를 수행하고 성공 backend와 실패 사유를 반환합니다."""
    failures: list[str] = []
    for backend in get_runtime_fallback_chain():
        try:
            if probe(backend):
                return backend, failures
        except Exception as exc:
            failures.append(f"{backend}: {exc}")
        else:
            failures.append(f"{backend}: unavailable")
    return "unavailable", failures


def select_runtime_backend(
    backend_status: Mapping[str, bool] | None = None,
) -> str:
    """기록된 실제 probe 결과를 사용해 vLLM -> CUDA -> CPU 순으로 선택합니다."""
    status = dict(backend_status or get_runtime_profile().get("runtime_backend_status", {}))
    for backend in get_runtime_fallback_chain():
        if status.get(backend) is True:
            return backend
    return "unavailable"
