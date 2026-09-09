"""
PILOS Redis Asynchronous Job Queue & Distributed Lock (Spec 019 / T013).
Provides lightweight, reliable background job queuing (LPUSH/BRPOP)
and Redlock pattern distributed locking with automatic expiration.
"""

import os
import json
import time
import uuid
from typing import Optional, Dict, Any, List

try:
    import redis
except ImportError:
    redis = None


class RedisJobQueue:
    """Asynchronous job queue using Redis LPUSH / BRPOP pattern with in-memory fallback."""

    def __init__(
        self,
        queue_name: str = "queue:pilos:jobs",
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 2.0
    ):
        self.queue_name = queue_name
        self.host = host or os.environ.get("REDIS_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("REDIS_PORT", 6379))
        self.db = db
        self.password = password or os.environ.get("REDIS_PASSWORD", None)
        self.socket_timeout = socket_timeout

        self._client = None
        self._local_queue: List[Dict[str, Any]] = []

    def _get_client(self):
        if redis is None:
            return None
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    socket_timeout=self.socket_timeout,
                    decode_responses=True,
                    retry=None
                )
            except Exception:
                self._client = None
        return self._client

    def enqueue(self, payload: Dict[str, Any]) -> bool:
        """Pushes a job payload to the Redis queue."""
        if "enqueued_at" not in payload:
            payload["enqueued_at"] = int(time.time())
        if "job_id" not in payload:
            payload["job_id"] = str(uuid.uuid4())

        client = self._get_client()
        if client:
            try:
                client.lpush(self.queue_name, json.dumps(payload, ensure_ascii=False))
                return True
            except Exception:
                pass

        # In-memory fallback
        self._local_queue.append(payload)
        return True

    def dequeue(self, timeout: int = 2) -> Optional[Dict[str, Any]]:
        """Blocks up to timeout seconds and pops next job payload."""
        client = self._get_client()
        if client:
            try:
                # BRPOP returns tuple (queue_name, item)
                res = client.brpop(self.queue_name, timeout=timeout)
                if res and len(res) == 2:
                    return json.loads(res[1])
            except Exception:
                pass

        # In-memory fallback
        if self._local_queue:
            return self._local_queue.pop(0)
        return None

    def length(self) -> int:
        """Returns number of pending jobs in queue."""
        client = self._get_client()
        if client:
            try:
                return client.llen(self.queue_name)
            except Exception:
                pass
        return len(self._local_queue)

    def clear(self) -> None:
        """Empties the queue."""
        client = self._get_client()
        if client:
            try:
                client.delete(self.queue_name)
            except Exception:
                pass
        self._local_queue.clear()


class RedisLock:
    """Distributed lock with automatic TTL release."""

    def __init__(
        self,
        lock_name: str,
        ttl_seconds: int = 30,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: int = 0
    ):
        self.lock_key = f"lock:pilos:{lock_name}" if not lock_name.startswith("lock:") else lock_name
        self.ttl_seconds = ttl_seconds
        self.token = str(uuid.uuid4())
        self.host = host or os.environ.get("REDIS_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("REDIS_PORT", 6379))
        self.db = db

        self._client = None
        self._local_locked = False

    def _get_client(self):
        if redis is None:
            return None
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    socket_timeout=1.0,
                    decode_responses=True,
                    retry=None
                )
            except Exception:
                self._client = None
        return self._client

    def acquire(self) -> bool:
        """Acquires the lock atomically using SET NX EX."""
        client = self._get_client()
        if client:
            try:
                # SET key val NX EX ttl
                ok = client.set(self.lock_key, self.token, nx=True, ex=self.ttl_seconds)
                return bool(ok)
            except Exception:
                pass

        # In-memory fallback
        if not self._local_locked:
            self._local_locked = True
            return True
        return False

    def release(self) -> bool:
        """Releases the lock if held by this instance token."""
        client = self._get_client()
        if client:
            try:
                # Lua script to release only if token matches
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                res = client.eval(lua_script, 1, self.lock_key, self.token)
                return bool(res)
            except Exception:
                pass

        self._local_locked = False
        return True


# Default singleton job queue instance
pilos_job_queue = RedisJobQueue()
