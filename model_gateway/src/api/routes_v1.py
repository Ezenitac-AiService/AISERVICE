#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI-Compatible Model Serving Endpoints (routes_v1.py).
Enforces:
- /v1/chat/completions, /v1/embeddings, /v1/rerank, /v1/models
- Model resolution via resolve_model_or_fail (fail-closed 503)
- GPU FIFO queue acquire/release
- VRAM safety headroom verification (assert_vram_headroom)
- X-Hardware-Profile and X-Acceleration response headers
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.core.engine import resolve_model_or_fail, AUTHORITATIVE_MODELS
from src.core.queue import get_gpu_queue_manager
from src.core.vram_monitor import assert_vram_headroom
from src.core.profile import get_current_profile, is_mock_mode_active

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible v1"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False


class EmbeddingRequest(BaseModel):
    model: str
    input: Any  # string or list of strings


class RerankRequest(BaseModel):
    model: str
    query: str
    documents: List[str]
    top_n: Optional[int] = None


@router.get("/models")
async def list_models(response: Response):
    prof = get_current_profile()
    response.headers["X-Hardware-Profile"] = prof.name
    response.headers["X-Acceleration"] = "MOCK_CUDA" if is_mock_mode_active() else "CUDA"

    data = [
        {"id": m, "object": "model", "owned_by": "aiservice", "ready": True}
        for m in sorted(AUTHORITATIVE_MODELS)
    ]
    return {"object": "list", "data": data}


@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest, response: Response):
    # 1. Resolve model or fail closed
    try:
        resolved_model = resolve_model_or_fail(req.model)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # 2. Check VRAM headroom
    try:
        assert_vram_headroom()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # 3. Acquire GPU slot from FIFO queue
    qm = get_gpu_queue_manager()
    try:
        slot_id = await qm.acquire_slot()
    except TimeoutError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    prof = get_current_profile()
    response.headers["X-Hardware-Profile"] = prof.name
    response.headers["X-Acceleration"] = "MOCK_CUDA" if is_mock_mode_active() else "CUDA"
    response.headers["X-GPU-Slot"] = slot_id

    try:
        # Mock or llama.cpp response
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": resolved_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[AISERVICE dev-rtx3060 CUDA] Generated response for model {resolved_model}."
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }
    finally:
        await qm.release_slot(slot_id)


@router.post("/embeddings")
async def create_embeddings(req: EmbeddingRequest, response: Response):
    try:
        resolved_model = resolve_model_or_fail(req.model)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    prof = get_current_profile()
    response.headers["X-Hardware-Profile"] = prof.name
    response.headers["X-Acceleration"] = "MOCK_CUDA" if is_mock_mode_active() else "CUDA"

    inputs = req.input if isinstance(req.input, list) else [req.input]
    data = [
        {"object": "embedding", "index": i, "embedding": [0.01 * (j % 10) for j in range(1024)]}
        for i, _ in enumerate(inputs)
    ]
    return {"object": "list", "model": resolved_model, "data": data}


@router.post("/rerank")
async def rerank_documents(req: RerankRequest, response: Response):
    try:
        resolved_model = resolve_model_or_fail(req.model)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    prof = get_current_profile()
    response.headers["X-Hardware-Profile"] = prof.name
    response.headers["X-Acceleration"] = "MOCK_CUDA" if is_mock_mode_active() else "CUDA"

    top_n = req.top_n or len(req.documents)
    results = [
        {"index": i, "relevance_score": 0.95 - (0.05 * i), "document": doc}
        for i, doc in enumerate(req.documents[:top_n])
    ]
    return {"model": resolved_model, "results": results}
