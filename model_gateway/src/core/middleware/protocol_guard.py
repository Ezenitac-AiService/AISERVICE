"""
Protocol SafeGuard ASGI middleware for vllm_serv (T005).
Sanitizes HTTP response headers to prevent h11.LocalProtocolError: Too little data for declared Content-Length.
"""

from starlette.types import ASGIApp, Scope, Receive, Send, Message


class ProtocolGuardMiddleware:
    """ASGI Middleware to strip invalid or mismatched Content-Length headers on streaming/chunked responses."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = message.get("headers", [])
                new_headers = []
                is_chunked = False
                
                # Scan headers for Transfer-Encoding: chunked
                for name, val in raw_headers:
                    if name.lower() == b"transfer-encoding" and b"chunked" in val.lower():
                        is_chunked = True
                        break

                for name, val in raw_headers:
                    # Strip Content-Length on chunked or streaming responses to prevent h11 protocol mismatch
                    if is_chunked and name.lower() == b"content-length":
                        continue
                    new_headers.append((name, val))
                
                message["headers"] = new_headers

            await send(message)

        await self.app(scope, receive, send_wrapper)
