"""
Unified AI Gateway Client (Spec 030 / Feature 008 — Refactored).
Async httpx.AsyncClient connection pool, non-blocking aiter_lines() SSE streaming,
BGE-M3 / BGE-Reranker-v2-m3 / Qwen 3.5 support with Redis L2/L3 cache and GPU semaphore guards.
"""

import asyncio
import json
import hashlib
import time
from typing import List, Dict, Any, Iterator, AsyncIterator, Optional

import httpx
import numpy as np

from .config import get_settings, CoreSettings
from .redis_pool import (
    cache_get, cache_set, build_l2_key, build_l3_key, get_redis_client,
)
from .logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.gateway")

# GPU Concurrency Semaphore (Spec 030 FR-027)
_gpu_semaphore: Optional[asyncio.Semaphore] = None


def _get_gpu_semaphore() -> asyncio.Semaphore:
    """Lazy global GPU concurrency semaphore (max=gpu_concurrency_limit)."""
    global _gpu_semaphore
    if _gpu_semaphore is None:
        settings = get_settings()
        _gpu_semaphore = asyncio.Semaphore(settings.gpu_concurrency_limit)
    return _gpu_semaphore


class AiGatewayClient:
    """Unified AI Gateway Client supporting both non-blocking async and legacy sync interfaces."""

    def __init__(
        self,
        settings: Optional[CoreSettings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.settings = settings or get_settings()
        self._client: Optional[httpx.AsyncClient] = client
        self._owns_client: bool = False

    async def _get_client(self) -> httpx.AsyncClient:
        """Returns injected or lazily initialized async HTTP connection pool."""
        if self._client is not None and not self._client.is_closed:
            return self._client
        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=30,
            keepalive_expiry=60.0,
        )
        self._client = httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        self._owns_client = True
        return self._client

    async def aclose(self):
        """Closes internal HTTP client if owned by this instance."""
        if self._owns_client and self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    @property
    def timeout_llm(self) -> float:
        return self.settings.timeout_llm_sec

    @property
    def inactivity_timeout_s(self) -> float:
        return self.settings.inactivity_timeout_s

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Embeddings (BGE-M3 on port 8081 /v1/embeddings) with Redis L2 Cache
    # ─────────────────────────────────────────────────────────────────────────

    async def aembed(self, texts: List[str], trace_id: str = "") -> List[List[float]]:
        """Asynchronously embeds a list of text strings via BGE-M3 gateway with Redis L2 cache."""
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

        # 2. Fetch missing embeddings via async httpx connection pool
        if missing_texts:
            url = f"{self.settings.embed_endpoint}/embeddings"
            payload = {
                "model": self.settings.embedding_model,
                "input": missing_texts,
            }
            client = await self._get_client()
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    timeout=self.settings.timeout_search_sec,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    fetched_vectors = [item["embedding"] for item in data.get("data", [])]
                    for m_idx, vec, text in zip(missing_indices, fetched_vectors, missing_texts):
                        results[m_idx] = vec
                        try:
                            cache_set(build_l2_key(text), vec, self.settings.redis_ttl_embedding)
                        except Exception:
                            pass
                else:
                    logger.warning(
                        f"원격 임베딩 HTTP 상태 이상: {resp.status_code}",
                        extra={"trace_id": trace_id or get_trace_id(), "status_code": resp.status_code},
                    )
            except Exception as e:
                logger.warning(
                    f"원격 임베딩 비동기 호출 실패: {e}",
                    extra={"trace_id": trace_id or get_trace_id(), "error_type": type(e).__name__},
                )

        return [v for v in results if v is not None]

    def embed(self, texts: List[str], trace_id: str = "") -> List[List[float]]:
        """Synchronous wrapper for legacy callers."""
        if not texts:
            return []
        try:
            asyncio.get_running_loop()
            with httpx.Client(timeout=self.settings.timeout_search_sec) as sync_client:
                url = f"{self.settings.embed_endpoint}/embeddings"
                payload = {"model": self.settings.embedding_model, "input": texts}
                resp = sync_client.post(url, json=payload)
                if resp.status_code == 200:
                    return [item["embedding"] for item in resp.json().get("data", [])]
                return []
        except RuntimeError:
            return asyncio.run(self.aembed(texts, trace_id))

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Reranker (BGE-Reranker on port 8081 /v1/rerank) with Redis L3 Cache
    # ─────────────────────────────────────────────────────────────────────────

    async def arerank(
        self,
        query: str,
        documents: List[str],
        timeout: float = 0.0,
        trace_id: str = "",
    ) -> Optional[List[float]]:
        """
        Scores query vs documents using BGE-Reranker GPU endpoint asynchronously.
        Returns raw logit scores from Cross-Encoder or None on failure/timeout.
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

        # 2. GPU Remote Reranking with Semaphore Guard
        sem = _get_gpu_semaphore()
        async with sem:
            client = await self._get_client()
            url = f"{self.settings.rerank_endpoint}/rerank"
            payload = {
                "model": self.settings.rerank_model,
                "query": query,
                "documents": list(documents),
            }
            try:
                resp = await client.post(url, json=payload, timeout=effective_timeout)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    results = resp_json.get("results") or resp_json.get("data") or []
                    scores = [0.0] * len(documents)
                    for item in results:
                        idx = item.get("index", 0)
                        if 0 <= idx < len(scores):
                            scores[idx] = float(item.get("relevance_score", 0.0))

                    # Save to Redis L3 (TTL: 24h)
                    try:
                        cache_set(cache_key, scores, self.settings.redis_ttl_rerank)
                    except Exception:
                        pass

                    return scores
                else:
                    logger.warning(
                        f"리랭커 HTTP 오류: {resp.status_code} {resp.text}",
                        extra={"trace_id": trace_id or get_trace_id(), "status_code": resp.status_code},
                    )
                    return None
            except Exception as e:
                logger.warning(
                    f"리랭커 비동기 타임아웃/장애 (안전 폴백 발동): {e}",
                    extra={
                        "trace_id": trace_id or get_trace_id(),
                        "fallback": True,
                        "error_type": type(e).__name__,
                    },
                )
                return None

    def rerank(
        self,
        query: str,
        documents: List[str],
        timeout: float = 0.0,
        trace_id: str = "",
    ) -> Optional[List[float]]:
        """Synchronous wrapper for legacy callers."""
        try:
            asyncio.get_running_loop()
            with httpx.Client(timeout=timeout or self.settings.timeout_rerank_sec) as sync_client:
                url = f"{self.settings.rerank_endpoint}/rerank"
                payload = {
                    "model": self.settings.rerank_model,
                    "query": query,
                    "documents": list(documents),
                }
                resp = sync_client.post(url, json=payload)
                if resp.status_code == 200:
                    results = resp.json().get("results") or []
                    scores = [0.0] * len(documents)
                    for item in results:
                        idx = item.get("index", 0)
                        if 0 <= idx < len(scores):
                            scores[idx] = float(item.get("relevance_score", 0.0))
                    return scores
                return None
        except RuntimeError:
            return asyncio.run(self.arerank(query, documents, timeout, trace_id))

    # ─────────────────────────────────────────────────────────────────────────
    # 3. LLM Token Stream (Qwen 3.5 on port 8081 /v1/chat/completions)
    # ─────────────────────────────────────────────────────────────────────────

    async def agenerate_stream(
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
    ) -> AsyncIterator[str]:
        """
        Non-blocking async token generator via SSE aiter_lines() with GPU semaphore guard.
        Protects against client aborts, orphan generations, and socket leaks.
        """
        temp = self.settings.default_temperature if temperature is None else temperature
        p_val = self.settings.default_top_p if top_p is None else top_p
        rep_pen = self.settings.default_repetition_penalty if repetition_penalty is None else repetition_penalty

        url = f"{self.settings.llm_endpoint}/chat/completions"
        payload = {
            "model": self.settings.synthesis_llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
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
        timeout_config = httpx.Timeout(
            timeout=inactivity_timeout,
            connect=10.0,
            read=inactivity_timeout,
            write=10.0,
            pool=10.0,
        )

        sem = _get_gpu_semaphore()
        async with sem:
            client = await self._get_client()
            try:
                async with client.stream("POST", url, json=payload, headers=headers, timeout=timeout_config) as resp:
                    if resp.status_code != 200:
                        err_text = await resp.aread()
                        raise ValueError(f"HTTP {resp.status_code}: {err_text.decode('utf-8', errors='ignore')}")

                    pending_event_type = None
                    async for line_str in resp.aiter_lines():
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
                            token = delta.get("content") or delta.get("reasoning_content") or ""
                            if token:
                                yield token
                        except Exception:
                            continue
            except asyncio.CancelledError:
                logger.info(
                    "LLM 스트리밍 클라이언트 연결 단절(CancelledError) 감지 — 정상 소켓 반환",
                    extra={"trace_id": trace_id or get_trace_id()},
                )
                raise
            except Exception as e:
                logger.error(
                    f"LLM 스트리밍 비동기 오류: {e}",
                    extra={"trace_id": trace_id or get_trace_id(), "error_type": type(e).__name__},
                )
                yield f"\n[답변 생성 오류: {e}]"

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
        """Synchronous token stream generator for legacy CLI/scripts."""
        temp = self.settings.default_temperature if temperature is None else temperature
        p_val = self.settings.default_top_p if top_p is None else top_p
        rep_pen = self.settings.default_repetition_penalty if repetition_penalty is None else repetition_penalty

        url = f"{self.settings.llm_endpoint}/chat/completions"
        payload = {
            "model": self.settings.synthesis_llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
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

        timeout_config = httpx.Timeout(
            timeout=self.settings.inactivity_timeout_s,
            connect=10.0,
            read=self.settings.inactivity_timeout_s,
            write=10.0,
            pool=10.0,
        )

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
                                    queue_callback(json.loads(data_str))
                                except Exception:
                                    pass
                            continue

                        pending_event_type = None

                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_obj = json.loads(data_str)
                            delta = chunk_obj["choices"][0].get("delta", {})
                            token = delta.get("content") or delta.get("reasoning_content") or ""
                            if token:
                                yield token
                        except Exception:
                            continue
        except Exception as e:
            logger.error(
                f"LLM 스트리밍 동기 오류: {e}",
                extra={"trace_id": trace_id or get_trace_id(), "error_type": type(e).__name__},
            )
            yield f"\n[답변 생성 오류: {e}]"


# Aliases for SSOT & backwards compatibility
ModelGatewayClient = AiGatewayClient
