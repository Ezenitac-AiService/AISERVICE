"""
Unified AI Gateway Client (Spec 030 — Refactored).
asyncio.Semaphore(3) GPU 동시성 가드, 5.0s 단일 리랭커 타임아웃, CPU 로컬 폴백 제거,
Redis L2/L3 캐시 연동, 비동기 httpx 전환.
"""

import asyncio
import json
import hashlib
import time
import urllib.request
import urllib.error
from typing import List, Dict, Any, Iterator, AsyncIterator, Optional

import httpx
import numpy as np

from .config import get_settings
from .redis_pool import (
    cache_get, cache_set, build_l2_key, build_l3_key, get_redis_client,
)
from .logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.gateway")

# GPU 동시성 제어 세마포어 (Spec 030 FR-027)
_gpu_semaphore: Optional[asyncio.Semaphore] = None


def _get_gpu_semaphore() -> asyncio.Semaphore:
    """전역 GPU 동시성 세마포어 (Lazy init, max=3)."""
    global _gpu_semaphore
    if _gpu_semaphore is None:
        settings = get_settings()
        _gpu_semaphore = asyncio.Semaphore(settings.gpu_concurrency_limit)
    return _gpu_semaphore


class AiGatewayClient:
    """Unified HTTP Client with Synchronous & Asynchronous method pairs."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Embeddings (BGE-M3 on port 8090) with Redis Layer 2 Cache
    # ─────────────────────────────────────────────────────────────────────────

    def embed(self, texts: List[str], trace_id: str = "") -> List[List[float]]:
        """Synchronously embeds a list of text strings via BGE-M3 remote gateway with Redis L2 cache."""
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        missing_indices: List[int] = []
        missing_texts: List[str] = []

        # 1. Check Redis L2 Cache
        for idx, text in enumerate(texts):
            try:
                key = build_l2_key(text)
                cached = cache_get(key)
                if cached is not None:
                    results[idx] = cached
                else:
                    missing_indices.append(idx)
                    missing_texts.append(text)
            except Exception:
                missing_indices.append(idx)
                missing_texts.append(text)

        # 2. Fetch missing from remote gateway
        if missing_texts:
            url = f"{self.settings.embed_endpoint}/embeddings"
            payload = json.dumps({"model": self.settings.embedding_model, "input": missing_texts}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.settings.timeout_search_sec) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    fetched_vectors = [item["embedding"] for item in data.get("data", [])]
                    for m_idx, vec, text in zip(missing_indices, fetched_vectors, missing_texts):
                        results[m_idx] = vec
                        # Save to Redis L2 (TTL: 7 days)
                        try:
                            cache_set(build_l2_key(text), vec, self.settings.redis_ttl_embedding)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(
                    f"원격 임베딩 실패: {e}",
                    extra={"trace_id": trace_id or get_trace_id(), "error_type": type(e).__name__},
                )
                return [v for v in results if v is not None]

        return [v for v in results if v is not None]

    async def aembed(self, texts: List[str], trace_id: str = "") -> List[List[float]]:
        """Asynchronously embeds a list of text strings."""
        return self.embed(texts, trace_id)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Reranker (BGE-Reranker on port 8091) — Spec 030 Refactored
    #    5.0s 단일 타임아웃, CPU 로컬 폴백 완전 제거, Redis L3 캐시
    # ─────────────────────────────────────────────────────────────────────────

    def rerank(
        self,
        query: str,
        documents: List[str],
        timeout: float = 0.0,
        trace_id: str = "",
    ) -> Optional[List[float]]:
        """
        Scores query vs documents using BGE-Reranker GPU endpoint (Spec 030).

        - 단일 통합 배치 리랭킹 (다중 타겟의 후보군을 1회로 병합)
        - 5.0s 단일 타임아웃 초과 시 None 반환 (0ms 1차 유사도 순위 유지)
        - CPU 로컬 CrossEncoder 폴백 완전 제거 (FR-007)
        - Redis L3 캐시 조회/저장 연동

        Returns:
            List[float] on success, None on timeout/failure (triggers safe fallback).
        """
        if not documents:
            return []

        effective_timeout = timeout if timeout > 0 else self.settings.timeout_rerank_sec

        # 1. Check Redis L3 Cache
        q_norm = " ".join(query.strip().lower().split())
        docs_str = "||".join(documents)
        cache_key = build_l3_key(q_norm, docs_str)

        cached = cache_get(cache_key)
        if cached is not None:
            logger.info(
                "리랭커 L3 캐시 히트",
                extra={"trace_id": trace_id or get_trace_id(), "cache_hit": True},
            )
            return cached

        # 2. GPU Remote Reranking (5.0s 단일 타임아웃)
        all_texts = [query] + list(documents)
        url = f"{self.settings.rerank_endpoint}/embeddings"
        payload = json.dumps({
            "model": self.settings.rerank_model,
            "input": all_texts
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                data_items = resp_json.get("data", [])
                if len(data_items) < len(all_texts):
                    return None

                def _to_1d(arr):
                    v = np.array(arr, dtype=np.float32)
                    while v.ndim > 1:
                        v = v.mean(axis=0)
                    return v

                q_vec = _to_1d(data_items[0]["embedding"])
                norm_q = np.linalg.norm(q_vec) + 1e-9

                scores = []
                for i in range(1, len(all_texts)):
                    d_vec = _to_1d(data_items[i]["embedding"])
                    norm_d = np.linalg.norm(d_vec) + 1e-9
                    sim = float(np.dot(q_vec, d_vec) / (norm_q * norm_d))
                    scores.append(max(0.0, min(1.0, (sim + 1.0) / 2.0)))

                # Save to Redis L3 (TTL: 24h)
                cache_set(cache_key, scores, self.settings.redis_ttl_rerank)

                return scores

        except Exception as e:
            # Spec 030 FR-007: 타임아웃 또는 장애 시 None 반환 → 0ms 1차 유사도 폴백
            logger.warning(
                f"리랭커 타임아웃/장애 (안전 폴백 발동): {e}",
                extra={
                    "trace_id": trace_id or get_trace_id(),
                    "fallback": True,
                    "error_type": type(e).__name__,
                },
            )
            return None

    async def arerank(
        self,
        query: str,
        documents: List[str],
        timeout: float = 0.0,
        trace_id: str = "",
    ) -> Optional[List[float]]:
        """Asynchronously scores query vs documents with GPU semaphore guard."""
        sem = _get_gpu_semaphore()
        async with sem:
            return self.rerank(query, documents, timeout, trace_id)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. LLM Token Stream (Qwen3.5 on port 8081) — Spec 030 Enhanced
    # ─────────────────────────────────────────────────────────────────────────

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "당신은 올리브영 뷰티 리뷰 분석 AI 어시스턴트 '올리뷰'입니다.",
        max_tokens: int = 4096,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        repetition_penalty: Optional[float] = None,
        trace_id: str = "",
        tenant_id: str = "default",
        session_id: str = "",
        queue_callback=None,
    ) -> Iterator[str]:
        """Yields streaming tokens from LLM via SSE (Spec 031 & Spec 037: Sliding Inactivity Timeout + 2-Stage Top-P).

        Args:
            queue_callback: Optional callable(dict) invoked on each `event: queue_status` event
                            to relay queue position/wait info to the UI layer.
        """
        temp = self.settings.default_temperature if temperature is None else temperature
        p_val = self.settings.default_top_p if top_p is None else top_p
        rep_pen = self.settings.default_repetition_penalty if repetition_penalty is None else repetition_penalty

        url = f"{self.settings.llm_endpoint}/chat/completions"
        payload = {
            "model": self.settings.synthesis_llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temp,
            "top_p": p_val,
            "repetition_penalty": rep_pen,
            "stream": True,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "X-Tenant-Id": tenant_id,
            "X-Session-Id": session_id,
        }

        inactivity_timeout = self.settings.inactivity_timeout_s
        timeout_config = httpx.Timeout(timeout=inactivity_timeout, connect=10.0, read=inactivity_timeout)

        try:
            with httpx.Client(timeout=timeout_config) as client:
                with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        err_text = resp.read().decode("utf-8", errors="ignore")
                        raise ValueError(f"HTTP {resp.status_code}: {err_text}")

                    pending_event_type = None
                    for line_str in resp.iter_lines():
                        line_str = line_str.strip()
                        if not line_str or line_str.startswith(":"):
                            continue

                        if line_str.startswith("event:"):
                            pending_event_type = line_str[6:].strip()
                            continue

                        if not line_str.startswith("data:"):
                            continue

                        data_str = line_str[5:].strip()

                        if pending_event_type == "queue_status":
                            pending_event_type = None
                            if queue_callback and data_str:
                                try:
                                    status_data = json.loads(data_str)
                                    queue_callback(status_data)
                                except Exception:
                                    pass
                            continue

                        pending_event_type = None

                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_obj = json.loads(data_str)
                            delta = chunk_obj["choices"][0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                yield token
                        except Exception:
                            continue
        except Exception as e:
            logger.error(
                f"LLM 스트리밍 오류: {e}",
                extra={"trace_id": trace_id or get_trace_id(), "error_type": type(e).__name__},
            )
            yield f"\n[답변 생성 오류: {e}]"

    async def agenerate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        trace_id: str = "",
    ) -> AsyncIterator[str]:
        """Asynchronous generator of tokens with GPU semaphore guard."""
        sem = _get_gpu_semaphore()
        async with sem:
            for token in self.generate_stream(prompt, system_prompt, max_tokens, trace_id=trace_id):
                yield token
