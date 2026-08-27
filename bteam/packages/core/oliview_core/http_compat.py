"""HTTP/SSE compatibility surface shared by the two Green chatbot services."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import unquote, urlsplit

from .chat import ChatEngine


def _route_path(raw_path: str) -> str:
    return urlsplit(raw_path).path.rstrip("/") or "/"


def _session_id_from_path(path: str, *, require_history: bool = True) -> str | None:
    parts = [unquote(part) for part in path.split("/")]
    try:
        index = parts.index("session")
    except ValueError:
        return None
    if index + 2 < len(parts) and parts[index + 2] == "history":
        return parts[index + 1]
    if not require_history and index + 1 < len(parts):
        return parts[index + 1]
    return None


def build_handler(service_name: str) -> type[BaseHTTPRequestHandler]:
    engine = ChatEngine()

    class CompatibilityHandler(BaseHTTPRequestHandler):
        chat_engine = engine

        def _send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_payload(self) -> dict[str, object] | None:
            try:
                length = max(
                    0, min(int(self.headers.get("Content-Length", "0")), 2_000_000)
                )
                payload = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError, json.JSONDecodeError):
                self._send_json(400, {"error": "invalid_json"})
                return None
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "json_object_required"})
                return None
            return payload

        def do_GET(self) -> None:
            path = _route_path(self.path)
            if path in {"/", "/health", "/healthz"}:
                self._send_json(
                    200,
                    {"status": "ok", "service": service_name, "version": "2.0.0"},
                )
                return
            session_id = _session_id_from_path(path)
            if session_id is not None:
                messages = self.chat_engine.session_store.get_messages(session_id)
                self._send_json(
                    200,
                    {
                        "session_id": session_id,
                        "messages": messages,
                        "count": len(messages),
                    },
                )
                return
            self._send_json(404, {"error": "not_found"})

        def do_DELETE(self) -> None:
            path = _route_path(self.path)
            session_id = _session_id_from_path(path, require_history=False)
            if session_id is None:
                self._send_json(404, {"error": "not_found"})
                return
            self.chat_engine.session_store.clear_session(session_id)
            self._send_json(200, {"session_id": session_id, "status": "cleared"})

        def do_POST(self) -> None:
            path = _route_path(self.path)
            supported = (
                "/api/v1/chat",
                "/api/v1/chat/stream",
                "/api/v1/search/stream",
            )
            if not any(path.endswith(route) for route in supported):
                self._send_json(404, {"error": "not_found"})
                return
            payload = self._read_payload()
            if payload is None:
                return
            trace_id = self.headers.get("X-Trace-Id") or None
            is_stream = path.endswith("/stream")
            if is_stream:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                # This compatibility stream is finite; close it explicitly so
                # legacy clients do not wait forever for a missing length.
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                self.close_connection = True
                try:
                    for event in self.chat_engine.stream(
                        payload,
                        service=service_name,
                        trace_id=trace_id,
                    ):
                        event_type = str(event.get("event_type", "message"))
                        data = json.dumps(event, ensure_ascii=False)
                        self.wfile.write(
                            f"event: {event_type}\ndata: {data}\n\n".encode()
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
                return
            response = self.chat_engine.respond(
                payload, service=service_name, trace_id=trace_id
            )
            self._send_json(200, response)

        def log_message(self, *_args: Any) -> None:
            return

    CompatibilityHandler.__name__ = (
        f"{service_name.title().replace('_', '')}CompatibilityHandler"
    )
    return CompatibilityHandler
