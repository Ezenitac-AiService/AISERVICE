# Interface Contract: Redis Client & Service Interfaces (Spec 019)

## 1. Redis Cache & Client Interface (`BaseRedisManager`)

```python
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

class BaseRedisManager(ABC):
    """Abstract interface for Redis Caching, Session & Queue management."""

    @abstractmethod
    async def get_embedding(self, model_id: str, text: str) -> Optional[List[float]]:
        """Returns cached embedding vector or None."""
        pass

    @abstractmethod
    async def set_embedding(self, model_id: str, text: str, vector: List[float], ttl: int = 604800) -> None:
        """Stores embedding vector with TTL."""
        pass

    @abstractmethod
    async def get_session_history(self, session_id: str, max_messages: int = 20) -> List[Dict[str, str]]:
        """Retrieves multi-turn conversation messages."""
        pass

    @abstractmethod
    async def append_session_message(self, session_id: str, role: str, content: str, ttl: int = 259200) -> None:
        """Appends a new chat message to session and refreshes TTL."""
        pass

    @abstractmethod
    async def enqueue_job(self, queue_name: str, payload: Dict[str, Any]) -> None:
        """Pushes a background job to Redis queue."""
        pass

    @abstractmethod
    async def dequeue_job(self, queue_name: str, timeout: int = 5) -> Optional[Dict[str, Any]]:
        """Blocks and pops next job from Redis queue."""
        pass

    @abstractmethod
    async def acquire_lock(self, lock_key: str, token: str, timeout_ms: int = 30000) -> bool:
        """Acquires a distributed lock with automatic expiration."""
        pass

    @abstractmethod
    async def release_lock(self, lock_key: str, token: str) -> bool:
        """Releases the lock if token matches."""
        pass

    @abstractmethod
    async def check_rate_limit(self, client_id: str, max_requests: int = 20, window_s: int = 1) -> bool:
        """Returns True if request is within rate limit, False if exceeded."""
        pass
```

---

## 2. Gateway & Observability Endpoints Contract

### `GET /health/redis`
```json
{
  "status": "healthy",
  "redis_version": "7.4.2",
  "uptime_in_seconds": 86400,
  "connected_clients": 5,
  "used_memory_human": "28.4M",
  "maxmemory_human": "256.0M",
  "keyspace": {
    "embedding_keys": 1420,
    "rerank_keys": 580,
    "session_keys": 42,
    "queue_jobs_pending": 0
  },
  "cache_hit_rate": {
    "embedding_hit_ratio": 0.88,
    "rerank_hit_ratio": 0.79
  }
}
```
