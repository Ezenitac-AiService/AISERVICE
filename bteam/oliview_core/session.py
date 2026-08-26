"""
Redis-backed Distributed Chat Session Store (Spec 019 / 030 / 035).
Manages multi-turn conversation context for Streamlit (ChatA) & FastAPI (ChatB)
with hierarchical memory summary, Anaphora metadata, and On-Demand Deep Recall (Redis L4).
"""

import os
import json
import time
from typing import List, Dict, Any, Optional

from .graph_state import AnaphoraTurnTag, DeepRecallTurnPayload

try:
    import redis
except ImportError:
    redis = None


class RedisSessionStore:
    """Multi-turn conversation session store backed by Redis list & TTL sliding window."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 1.0,
        default_ttl_seconds: int = 259200,  # 3 days
    ):
        self.host = host or os.environ.get("REDIS_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("REDIS_PORT", 6379))
        self.db = db
        self.password = password or os.environ.get("REDIS_PASSWORD", None)
        self.socket_timeout = socket_timeout
        self.default_ttl = default_ttl_seconds

        self._redis_client = None
        self._local_fallback_store: Dict[str, List[Dict[str, Any]]] = {}
        self._local_turn_payloads: Dict[str, Dict[int, Dict[str, Any]]] = {}

    def _get_client(self):
        if redis is None:
            return None
        if self._redis_client is None:
            try:
                self._redis_client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    socket_timeout=self.socket_timeout,
                    decode_responses=True,
                    retry=None
                )
            except Exception:
                self._redis_client = None
        return self._redis_client

    def _get_session_key(self, session_id: str) -> str:
        return f"session:{session_id}:history"

    def _get_turn_payload_key(self, session_id: str, turn_index: int) -> str:
        return f"session:{session_id}:turn:{turn_index}"

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        max_messages: int = 30,
        ttl: Optional[int] = None,
        is_blocked: bool = False
    ) -> None:
        """
        Appends a new message item to session history and trims oldest messages beyond max_messages.
        """
        if is_blocked:
            return

        client = self._get_client()
        msg_obj = {
            "role": role,
            "content": content,
            "timestamp": int(time.time())
        }
        msg_str = json.dumps(msg_obj, ensure_ascii=False)
        ttl = ttl or self.default_ttl

        if client:
            try:
                key = self._get_session_key(session_id)
                pipe = client.pipeline()
                pipe.rpush(key, msg_str)
                pipe.ltrim(key, -max_messages, -1)
                pipe.expire(key, ttl)
                pipe.execute()
                return
            except Exception:
                pass

        # In-memory fallback
        if session_id not in self._local_fallback_store:
            self._local_fallback_store[session_id] = []
        self._local_fallback_store[session_id].append(msg_obj)
        if len(self._local_fallback_store[session_id]) > max_messages:
            self._local_fallback_store[session_id] = self._local_fallback_store[session_id][-max_messages:]

    def append_turn_payload(
        self,
        session_id: str,
        turn_index: int,
        user_query: str,
        assistant_response: str,
        reference_specs: Optional[List[Dict[str, Any]]] = None,
        reference_reviews: Optional[List[Dict[str, Any]]] = None,
        ttl: Optional[int] = None,
    ) -> None:
        """
        과거 턴 원본 페이로드(스펙/리뷰)를 Redis L4에 독립 키로 보존하여 On-Demand Deep Recall을 지원합니다.
        """
        payload = {
            "turn_index": turn_index,
            "user_query": user_query,
            "assistant_response": assistant_response,
            "reference_specs": reference_specs or [],
            "reference_reviews": reference_reviews or [],
            "recalled_at": time.time(),
        }
        ttl = ttl or self.default_ttl
        client = self._get_client()

        if client:
            try:
                key = self._get_turn_payload_key(session_id, turn_index)
                client.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl)
                return
            except Exception:
                pass

        if session_id not in self._local_turn_payloads:
            self._local_turn_payloads[session_id] = {}
        self._local_turn_payloads[session_id][turn_index] = payload

    def get_turn_payload(self, session_id: str, turn_index: int) -> Optional[DeepRecallTurnPayload]:
        """
        Redis L4에서 특정 과거 턴의 원본 페이로드를 온디맨드로 역조회합니다.
        """
        client = self._get_client()
        if client:
            try:
                key = self._get_turn_payload_key(session_id, turn_index)
                raw = client.get(key)
                if raw:
                    data = json.loads(raw)
                    return DeepRecallTurnPayload(**data)
            except Exception:
                pass

        if session_id in self._local_turn_payloads and turn_index in self._local_turn_payloads[session_id]:
            return DeepRecallTurnPayload(**self._local_turn_payloads[session_id][turn_index])
        return None

    def get_messages(self, session_id: str, max_messages: int = 30) -> List[Dict[str, Any]]:
        """Retrieves conversation history list for the given session ID."""
        client = self._get_client()
        if client:
            try:
                key = self._get_session_key(session_id)
                raw_items = client.lrange(key, -max_messages, -1)
                if raw_items:
                    client.expire(key, self.default_ttl)
                    return [json.loads(item) for item in raw_items]
            except Exception:
                pass

        return self._local_fallback_store.get(session_id, [])

    def clear_session(self, session_id: str) -> None:
        """Clears session history from Redis and local memory."""
        client = self._get_client()
        if client:
            try:
                key = self._get_session_key(session_id)
                client.delete(key)
                client.delete(f"checkpoint:{session_id}")
            except Exception:
                pass
        self._local_fallback_store.pop(session_id, None)
        self._local_turn_payloads.pop(session_id, None)

    # ─────────────────────────────────────────────────────────────────────────
    # LangGraph State Checkpoint (L4 Cache)
    # ─────────────────────────────────────────────────────────────────────────

    def save_checkpoint(self, session_id: str, state_dict: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        client = self._get_client()
        ttl = ttl or self.default_ttl
        ckpt_key = f"checkpoint:{session_id}"
        serializable = {}
        for k, v in state_dict.items():
            try:
                json.dumps(v)
                serializable[k] = v
            except (TypeError, OverflowError):
                pass

        if client:
            try:
                client.set(ckpt_key, json.dumps(serializable, ensure_ascii=False), ex=ttl)
                return True
            except Exception:
                pass
        return False

    def get_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        client = self._get_client()
        ckpt_key = f"checkpoint:{session_id}"
        if client:
            try:
                raw = client.get(ckpt_key)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return None


# Default singleton instance
session_store = RedisSessionStore()
