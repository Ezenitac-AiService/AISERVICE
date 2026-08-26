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

import numpy as np

from .config import get_settings, ModelDiscoveryCache
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
        self._discovery_cache = ModelDiscoveryCache(
            discovered_model=self.settings.synthesis_llm_model,
            discovered_n_ctx=self.settings.min_required_n_ctx,
            ttl_seconds=self.settings.discovery_ttl_seconds,
        )

    def discover_active_model(self, force_refresh: bool = False) -> str:
        """Dynamically discovers active model from Gateway with 60s TTL caching (Spec 033)."""
        if not self.settings.auto_discover_model:
            return self.settings.synthesis_llm_model

        if not force_refresh and self._discovery_cache.is_valid():
            return self._discovery_cache.discovered_model

        try:
            url = f"{self.settings.llm_endpoint}/models"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                active_llm = None
                for m in models:
                    if isinstance(m, dict):
                        m_id = m.get("id", "")
                        if "bge" not in m_id.lower() and (m.get("is_active") or m.get("is_resident")):
                            active_llm = m_id
                            n_ctx = m.get("current_n_ctx", 16384)
                            self._discovery_cache.update(m_id, n_ctx)
                            break

                if not active_llm:
                    for m in models:
                        if isinstance(m, dict):
                            m_id = m.get("id", "")
                            if "bge" not in m_id.lower():
                                active_llm = m_id
                                self._discovery_cache.update(m_id, 16384)
                                break

                if active_llm:
                    return active_llm
        except Exception as e:
            logger.warning(
                f"Failed to discover active model dynamically ({e}). Using default: {self.settings.synthesis_llm_model}"
            )

        return self.settings.synthesis_llm_model

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
        temperature: float = 0.1,
        trace_id: str = "",
        tenant_id: str = "default",
        session_id: str = "",
        queue_callback=None,
    ) -> Iterator[str]:
        """Yields streaming tokens from LLM via SSE (Spec 031: Sliding Inactivity Timeout + Queue Status).

        Args:
            queue_callback: Optional callable(dict) invoked on each `event: queue_status` event
                            to relay queue position/wait info to the UI layer.
        """
        url = f"{self.settings.llm_endpoint}/chat/completions"
        model_to_use = self.discover_active_model() if self.settings.auto_discover_model else self.settings.synthesis_llm_model
        payload = json.dumps({
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "X-Tenant-Id": tenant_id,
            "X-Session-Id": session_id,
        }

        req = urllib.request.Request(url, data=payload, headers=headers)

        try:
            # Spec 031 FR-004: Sliding Inactivity Timeout (마지막 패킷 수신 후 15초 무응답)
            inactivity_timeout = self.settings.inactivity_timeout_s
            resp = urllib.request.urlopen(req, timeout=inactivity_timeout)

            pending_event_type = None
            for line in resp:
                line_str = line.decode("utf-8").strip()

                # Spec 031 FR-002: Keep-Alive 하트비트 수신 시 리스 갱신 (타임아웃 리셋)
                if not line_str or line_str.startswith(":"):
                    # `: keepalive` 코멘트 — 연결 유지 확인, 타임아웃 리셋됨
                    continue

                # SSE event type 파싱
                if line_str.startswith("event:"):
                    pending_event_type = line_str[6:].strip()
                    continue

                if not line_str.startswith("data:"):
                    continue

                data_str = line_str[5:].strip()

                # Spec 031 FR-003: queue_status 이벤트 처리
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
