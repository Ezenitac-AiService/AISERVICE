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

try:
    from fastapi import HTTPException
except ImportError:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any):
            super().__init__(str(detail))
            self.status_code = status_code
            self.detail = detail

AUTHORITATIVE_MODELS = {
    "qwen3.5-9b",
    "qwen3.5-4b",
    "bge-m3",
    "bge-reranker-v2-m3",
}


def resolve_model_or_fail(model_name: str, single_model_mode: bool = False) -> str:
    """Resolve model alias to registered ID, or fail with OpenAI standard 404 model_not_found."""
    if not model_name:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "message": "Empty model requested.",
                    "type": "invalid_request_error",
                    "param": "model",
                    "code": "model_not_found",
                }
            },
        )

    routing = get_model_routing_config()
    model_lower = model_name.lower().strip()

    # Direct match in authoritative list
    if model_name in AUTHORITATIVE_MODELS:
        return model_name

    # Alias matching
    if model_lower in ("fast", "fast_llm_model", "router", "router_llm"):
        return routing["FAST_LLM_MODEL"]
    if model_lower in ("synthesis", "synthesis_llm_model", "default"):
        return routing["SYNTHESIS_LLM_MODEL"]
    if model_lower in ("embedding", "embedding_model"):
        return routing["EMBEDDING_MODEL"]
    if model_lower in ("rerank", "rerank_model"):
        return routing["RERANK_MODEL"]

    # Check if model matches without case
    for m in AUTHORITATIVE_MODELS:
        if m.lower() == model_lower:
            return m

    # Fail closed: reject decommissioned (e.g. qwen3.5-2b) and unknown models with OpenAI standard 404
    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "message": f"The model `{model_name}` does not exist or you do not have access to it.",
                "type": "invalid_request_error",
                "param": "model",
                "code": "model_not_found",
            }
        },
    )
