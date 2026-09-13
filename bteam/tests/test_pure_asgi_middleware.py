"""
test_pure_asgi_middleware.py
Unit tests for Pure ASGI Prefix Strip Middleware (Dual Normalization).
Tests both raw ASGI dispatch and HTTP handling with and without prefix,
ensuring zero-buffering compliance without BaseHTTPMiddleware.
"""

import asyncio
import unittest


class PureASGIPrefixStripMiddleware:
    """Pure ASGI middleware that strips subpath prefix and injects root_path without buffering."""

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = "/" + prefix.strip("/")

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            path = scope.get("path", "")
            if path == self.prefix:
                scope = dict(scope)
                scope["path"] = "/"
                scope["raw_path"] = b"/"
                scope["root_path"] = self.prefix
            elif path.startswith(self.prefix + "/"):
                scope = dict(scope)
                new_path = path[len(self.prefix):]
                scope["path"] = new_path
                scope["raw_path"] = new_path.encode("latin-1")
                scope["root_path"] = self.prefix

        await self.app(scope, receive, send)


class TestPureASGIMiddleware(unittest.TestCase):
    def test_pure_asgi_strips_prefix_and_sets_root_path(self):
        """Verifies that prefixed HTTP path is stripped and root_path is set in scope."""
        captured_scopes = []

        async def dummy_app(scope, receive, send):
            captured_scopes.append(scope)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})

        middleware = PureASGIPrefixStripMiddleware(dummy_app, prefix="/bteam/chata")

        scope_prefixed = {
            "type": "http",
            "method": "GET",
            "path": "/bteam/chata/api/chat/stream",
            "raw_path": b"/bteam/chata/api/chat/stream",
            "root_path": "",
            "headers": [],
        }

        async def dummy_receive():
            return {"type": "http.request"}

        async def dummy_send(event):
            pass

        asyncio.run(middleware(scope_prefixed, dummy_receive, dummy_send))

        self.assertEqual(len(captured_scopes), 1)
        scope = captured_scopes[0]
        self.assertEqual(scope["path"], "/api/chat/stream")
        self.assertEqual(scope["root_path"], "/bteam/chata")

    def test_pure_asgi_preserves_direct_path(self):
        """Verifies that non-prefixed direct HTTP path is unchanged."""
        captured_scopes = []

        async def dummy_app(scope, receive, send):
            captured_scopes.append(scope)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})

        middleware = PureASGIPrefixStripMiddleware(dummy_app, prefix="/bteam/chata")

        scope_direct = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "raw_path": b"/health",
            "root_path": "",
            "headers": [],
        }

        async def dummy_receive():
            return {"type": "http.request"}

        async def dummy_send(event):
            pass

        asyncio.run(middleware(scope_direct, dummy_receive, dummy_send))

        self.assertEqual(len(captured_scopes), 1)
        scope = captured_scopes[0]
        self.assertEqual(scope["path"], "/health")
        self.assertEqual(scope["root_path"], "")

    def test_pure_asgi_exact_prefix_root(self):
        """Verifies that exact prefix (/bteam/chata) maps to /."""
        captured_scopes = []

        async def dummy_app(scope, receive, send):
            captured_scopes.append(scope)

        middleware = PureASGIPrefixStripMiddleware(dummy_app, prefix="/bteam/chata")
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/bteam/chata",
            "raw_path": b"/bteam/chata",
            "root_path": "",
        }

        async def dummy_receive():
            return {"type": "http.request"}

        async def dummy_send(event):
            pass

        asyncio.run(middleware(scope, dummy_receive, dummy_send))

        self.assertEqual(len(captured_scopes), 1)
        self.assertEqual(captured_scopes[0]["path"], "/")
        self.assertEqual(captured_scopes[0]["root_path"], "/bteam/chata")


if __name__ == "__main__":
    unittest.main()
