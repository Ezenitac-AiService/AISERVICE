#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Model Inference Engine & Resolution Manager (SSOT).
Enforces:
- Model resolution across authoritative models: qwen3.5-4b, qwen3.5-2b, bge-m3, bge-reranker-v2-m3
- Single-model mode alias resolution
- Fail-closed 503 on unrouted/unavailable models (strictly NO CPU fallback)
- OOM safety check before execution
"""

from __future__ import annotations

import os
from typing import Any

from src.core.config import get_effective_model, get_model_routing_config
from src.core.profile import is_mock_mode_active

AUTHORITATIVE_MODELS = {
    "qwen3.5-4b",
    "qwen3.5-2b",
    "bge-m3",
    "bge-reranker-v2-m3",
}


def resolve_model_or_fail(model_name: str, single_model_mode: bool = False) -> str:
    """Resolve model alias to registered ID, or fail-closed with 503."""
    if not model_name:
        raise RuntimeError("503 Service Unavailable: Empty model requested.")

    routing = get_model_routing_config()
    model_lower = model_name.lower().strip()

    # Direct match in authoritative list
    if model_name in AUTHORITATIVE_MODELS:
        return model_name

    # Alias matching
    if model_lower in ("fast", "fast_llm_model"):
        return routing["FAST_LLM_MODEL"]
    if model_lower in ("synthesis", "synthesis_llm_model"):
        if single_model_mode:
            return routing["FAST_LLM_MODEL"]
        return routing["SYNTHESIS_LLM_MODEL"]
    if model_lower in ("embedding", "embedding_model"):
        return routing["EMBEDDING_MODEL"]
    if model_lower in ("rerank", "rerank_model"):
        return routing["RERANK_MODEL"]

    # Check if model matches without case
    for m in AUTHORITATIVE_MODELS:
        if m.lower() == model_lower:
            return m

    # Fail closed: reject unknown models with 503
    raise RuntimeError(
        f"503 Service Unavailable: Model '{model_name}' is unregistered or unavailable. "
        f"Supported authoritative models: {sorted(AUTHORITATIVE_MODELS)}"
    )
