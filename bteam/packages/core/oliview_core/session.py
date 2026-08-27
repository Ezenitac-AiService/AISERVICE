"""Small distributed session store used by both Green chatbot adapters.

The store speaks the tiny subset of Redis needed for chat history without adding
another runtime dependency to the shared Core package.  If Redis is unavailable,
the same interface falls back to a process-local store so a validation probe can
still exercise the full request lifecycle.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import unquote, urlsplit


class InMemorySessionStore:
    def __init__(self, *, default_ttl_seconds: int = 259200) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._messages: dict[str, list[dict[str, Any]]] = {}
        self._turn_payloads: dict[str, dict[int, dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        max_messages: int = 30,
        is_blocked: bool = False,
    ) -> None:
        if is_blocked:
            return
        message = {
            "role": str(role),
            "content": str(content),
            "timestamp": int(time.time()),
        }
        with self._lock:
            messages = self._messages.setdefault(str(session_id), [])
            messages.append(message)
            self._messages[str(session_id)] = messages[-max_messages:]

    def get_messages(
        self, session_id: str, *, max_messages: int = 30
    ) -> list[dict[str, Any]]:
        with self._lock:
            messages = self._messages.get(str(session_id), [])[-max_messages:]
            return [dict(message) for message in messages]

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._messages.pop(str(session_id), None)
            self._turn_payloads.pop(str(session_id), None)

    def append_turn_payload(
        self,
        session_id: str,
        turn_index: int,
        payload: dict[str, Any],
    ) -> None:
        with self._lock:
            self._turn_payloads.setdefault(str(session_id), {})[int(turn_index)] = dict(
                payload
            )

    def get_turn_payload(
        self, session_id: str, turn_index: int
    ) -> dict[str, Any] | None:
        with self._lock:
            payload = self._turn_payloads.get(str(session_id), {}).get(int(turn_index))
            return dict(payload) if payload is not None else None


class _RedisProtocolError(RuntimeError):
    pass


class RedisSessionStore(InMemorySessionStore):
    """Redis-backed history with safe local fallback on dependency failure."""

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        socket_timeout: float = 0.5,
        default_ttl_seconds: int = 259200,
        key_prefix: str = "bteam:session:",
    ) -> None:
        super().__init__(default_ttl_seconds=default_ttl_seconds)
        configured = endpoint or os.getenv("REDIS_ENDPOINT", "")
        parsed = urlsplit(configured) if configured else None
        self.host = (
            parsed.hostname
            if parsed and parsed.hostname
            else os.getenv("REDIS_HOST", "127.0.0.1")
        )
        self.port = int(
            parsed.port if parsed and parsed.port else os.getenv("REDIS_PORT", "6379")
        )
        redis_path = parsed.path if parsed is not None else "/0"
        self.database = int((redis_path or "/0").strip("/") or "0")
        self.password = (
            unquote(parsed.password)
            if parsed and parsed.password
            else os.getenv("REDIS_PASSWORD")
        )
        self.socket_timeout = socket_timeout
        self.key_prefix = key_prefix

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}{session_id}:history"

    @staticmethod
    def _encode_command(arguments: Iterable[object]) -> bytes:
        encoded = [str(argument).encode("utf-8") for argument in arguments]
        return (
            b"*"
            + str(len(encoded)).encode()
            + b"\r\n"
            + b"".join(
                b"$" + str(len(value)).encode() + b"\r\n" + value + b"\r\n"
                for value in encoded
            )
        )

    @staticmethod
    def _readline(connection: socket.socket) -> bytes:
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(1)
            if not chunk:
                raise _RedisProtocolError("Redis closed the connection")
            chunks.append(chunk)
            if b"".join(chunks).endswith(b"\r\n"):
                return b"".join(chunks)[:-2]

    @classmethod
    def _read_response(cls, connection: socket.socket) -> object:
        prefix = connection.recv(1)
        if not prefix:
            raise _RedisProtocolError("Redis returned an empty response")
        line = cls._readline(connection)
        if prefix == b"+":
            return line.decode("utf-8")
        if prefix == b"-":
            raise _RedisProtocolError(line.decode("utf-8", errors="replace"))
        if prefix == b":":
            return int(line)
        if prefix == b"$":
            length = int(line)
            if length < 0:
                return None
            value = b""
            while len(value) < length + 2:
                chunk = connection.recv(length + 2 - len(value))
                if not chunk:
                    raise _RedisProtocolError("Redis returned a truncated bulk value")
                value += chunk
            return value[:-2].decode("utf-8")
        if prefix == b"*":
            count = int(line)
            if count < 0:
                return None
            return [cls._read_response(connection) for _ in range(count)]
        raise _RedisProtocolError(f"Unsupported Redis response prefix: {prefix!r}")

    def _execute(self, *arguments: object) -> object:
        with socket.create_connection(
            (self.host, self.port), timeout=self.socket_timeout
        ) as connection:
            if self.password:
                connection.sendall(self._encode_command(("AUTH", self.password)))
                self._read_response(connection)
            if self.database:
                connection.sendall(self._encode_command(("SELECT", self.database)))
                self._read_response(connection)
            connection.sendall(self._encode_command(arguments))
            return self._read_response(connection)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        max_messages: int = 30,
        is_blocked: bool = False,
    ) -> None:
        if is_blocked:
            return
        message = json.dumps(
            {"role": str(role), "content": str(content), "timestamp": int(time.time())},
            ensure_ascii=False,
        )
        key = self._key(session_id)
        try:
            self._execute("RPUSH", key, message)
            self._execute("LTRIM", key, -max_messages, -1)
            self._execute("EXPIRE", key, self.default_ttl_seconds)
        except (OSError, _RedisProtocolError, ValueError):
            super().append_message(
                session_id,
                role,
                content,
                max_messages=max_messages,
                is_blocked=is_blocked,
            )

    def get_messages(
        self, session_id: str, *, max_messages: int = 30
    ) -> list[dict[str, Any]]:
        try:
            raw = self._execute("LRANGE", self._key(session_id), -max_messages, -1)
            if isinstance(raw, list):
                messages = [json.loads(item) for item in raw if isinstance(item, str)]
                if messages:
                    self._execute(
                        "EXPIRE", self._key(session_id), self.default_ttl_seconds
                    )
                return [message for message in messages if isinstance(message, dict)]
        except (
            OSError,
            _RedisProtocolError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            pass
        return super().get_messages(session_id, max_messages=max_messages)

    def clear_session(self, session_id: str) -> None:
        try:
            self._execute("DEL", self._key(session_id))
        except (OSError, _RedisProtocolError, ValueError):
            pass
        super().clear_session(session_id)


session_store = RedisSessionStore()
