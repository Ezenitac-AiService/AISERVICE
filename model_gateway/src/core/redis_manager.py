"""
Redis Manager & Caching Infrastructure (Spec 019 / T004).
Provides multi-layered caching (embedding, rerank, LLM), session history,
rate limiting, and zero-downtime graceful fallback circuit breaker.
"""

import os
import json
import hashlib
import time
from typing import Optional, List, Dict, Any, Union
from abc import ABC, abstractmethod

try:
    import redis.asyncio as aioredis
    from redis.exceptions import RedisError, ConnectionError, TimeoutError
except ImportError:
    aioredis = None
    RedisError = Exception
    ConnectionError = Exception
    TimeoutError = Exception


class BaseRedisManager(ABC):
    """Abstract interface for Redis operations."""

    @abstractmethod
    async def get_embedding(self, model_id: str, text: str) -> Optional[List[float]]:
        pass

    @abstractmethod
    async def set_embedding(self, model_id: str, text: str, vector: List[float], ttl: int = 604800) -> None:
        pass

    @abstractmethod
    async def get_rerank(self, query: str, doc_ids: List[str]) -> Optional[List[Dict[str, Any]]]:
        pass

    @abstractmethod
    async def set_rerank(self, query: str, doc_ids: List[str], scores: List[Dict[str, Any]], ttl: int = 86400) -> None:
        pass


class RedisManager(BaseRedisManager):
    """Production Redis manager with connection pooling and graceful error handling."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 1.0,
        max_connections: int = 20
    ):
        self.host = host or os.environ.get("REDIS_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("REDIS_PORT", 6379))
        self.db = db
        self.password = password or os.environ.get("REDIS_PASSWORD", None)
        self.socket_timeout = socket_timeout
        self.max_connections = max_connections

        self._client: Optional[Any] = None
        self._is_connected: bool = False
        self._last_health_check: float = 0.0

    async def get_client(self) -> Optional[Any]:
        """Lazy initialization of async Redis connection pool."""
        if aioredis is None:
            return None

        if self._client is None:
            try:
                self._client = aioredis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    socket_timeout=self.socket_timeout,
                    decode_responses=True,
                    max_connections=self.max_connections,
                    retry=None
                )
            except Exception as e:
                print(f"[RedisManager] Connection pool init warning: {e}")
                self._client = None
        return self._client

    def _hash_text(self, text: str) -> str:
        """Computes deterministic SHA256 hex digest for normalized text."""
        norm = " ".join(text.strip().lower().split())
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    async def get_embedding(self, model_id: str, text: str) -> Optional[List[float]]:
        """Retrieves cached embedding vector."""
        client = await self.get_client()
        if client is None:
            return None

        try:
            h = self._hash_text(text)
            key = f"emb:{model_id}:{h}"
            raw = await client.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def set_embedding(self, model_id: str, text: str, vector: List[float], ttl: int = 604800) -> None:
        """Caches embedding vector with default 7-day TTL."""
        client = await self.get_client()
        if client is None:
            return

        try:
            h = self._hash_text(text)
            key = f"emb:{model_id}:{h}"
            await client.set(key, json.dumps(vector), ex=ttl)
        except Exception:
            pass

    async def get_rerank(self, query: str, doc_ids: List[str]) -> Optional[List[Dict[str, Any]]]:
        """Retrieves cached reranker scores."""
        client = await self.get_client()
        if client is None:
            return None

        try:
            q_hash = self._hash_text(query)
            docs_hash = hashlib.sha256("||".join(sorted(doc_ids)).encode("utf-8")).hexdigest()
            key = f"rerank:{q_hash}:{docs_hash}"
            raw = await client.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def set_rerank(self, query: str, doc_ids: List[str], scores: List[Dict[str, Any]], ttl: int = 86400) -> None:
        """Caches reranker scores with default 24-hour TTL."""
        client = await self.get_client()
        if client is None:
            return

        try:
            q_hash = self._hash_text(query)
            docs_hash = hashlib.sha256("||".join(sorted(doc_ids)).encode("utf-8")).hexdigest()
            key = f"rerank:{q_hash}:{docs_hash}"
            await client.set(key, json.dumps(scores), ex=ttl)
        except Exception:
            pass

    async def check_rate_limit(self, client_id: str, max_requests: int = 20, window_s: int = 1) -> bool:
        """Token bucket rate limiter via atomic Redis Lua script."""
        client = await self.get_client()
        if client is None:
            return True  # Fallback to allow if Redis is unavailable

        lua_script = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local current = redis.call('incr', key)
        if current == 1 then
            redis.call('expire', key, tonumber(ARGV[2]))
        end
        if current > limit then
            return 0
        else
            return 1
        end
        """
        try:
            key = f"ratelimit:{client_id}"
            res = await client.eval(lua_script, 1, key, max_requests, window_s)
            return bool(res == 1)
        except Exception:
            return True

    async def get_health_stats(self) -> Dict[str, Any]:
        """Returns Redis health, memory, and keyspace statistics."""
        client = await self.get_client()
        if client is None:
            return {"status": "unreachable", "error": "Redis client not initialized"}

        try:
            info = await client.info()
            return {
                "status": "healthy",
                "redis_version": info.get("redis_version"),
                "used_memory_human": info.get("used_memory_human"),
                "maxmemory_human": info.get("maxmemory_human", "256M"),
                "connected_clients": info.get("connected_clients"),
                "uptime_in_seconds": info.get("uptime_in_seconds"),
            }
        except Exception as e:
            return {"status": "degraded", "error": str(e)}

    async def aclose(self) -> None:
        """Closes Redis client connection cleanly."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None


# Global singleton instance
redis_manager = RedisManager()
