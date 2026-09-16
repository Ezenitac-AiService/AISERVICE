import json
from typing import Callable

class RequestBodyLimitMiddleware:
    """Pure ASGI middleware enforcing request body size limit (2MB) with Content-Length and chunked abort (HTTP 413)."""

    def __init__(self, app: Callable, max_bytes: int = 2 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. Fast rejection via Content-Length header
        content_length_header = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                content_length_header = value
                break

        if content_length_header:
            try:
                content_length = int(content_length_header.decode("latin1"))
                if content_length > self.max_bytes:
                    await self._send_413(send, f"Request body size ({content_length} bytes) exceeds limit of {self.max_bytes} bytes.")
                    return
            except (ValueError, UnicodeDecodeError):
                pass

        # 2. Chunked streaming guard for chunked transfer-encoding
        bytes_received = 0
        limit_exceeded = False

        async def receive_wrapper():
            nonlocal bytes_received, limit_exceeded
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                bytes_received += len(chunk)
                if bytes_received > self.max_bytes:
                    limit_exceeded = True
                    raise RequestBodyTooLargeError(bytes_received, self.max_bytes)
            return message

        try:
            await self.app(scope, receive_wrapper, send)
        except RequestBodyTooLargeError as exc:
            await self._send_413(send, str(exc))

    async def _send_413(self, send, message: str):
        payload = json.dumps({
            "error": {
                "message": message,
                "type": "payload_too_large_error",
                "code": "request_body_too_large"
            }
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("latin1")),
            ]
        })
        await send({
            "type": "http.response.body",
            "body": payload,
            "more_body": False
        })


class RequestBodyTooLargeError(Exception):
    def __init__(self, size: int, limit: int):
        super().__init__(f"Request body exceeded limit of {limit} bytes (received {size} bytes).")
        self.size = size
        self.limit = limit
