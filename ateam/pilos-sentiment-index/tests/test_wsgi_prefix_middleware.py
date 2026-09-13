"""
test_wsgi_prefix_middleware.py
Tests Flask WSGI Prefix Strip Middleware (Dual Normalization).
Verifies that requests with prefix /ateam/pilos and direct requests without prefix
are both accepted and routed correctly.
"""

import unittest
from flask import Flask, jsonify, request


class WSGIPrefixStripMiddleware:
    """WSGI middleware to strip prefix while preserving SCRIPT_NAME."""
    def __init__(self, app, prefix="/ateam/pilos"):
        self.app = app
        self.prefix = prefix.rstrip("/")

    def __call__(self, environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        if path_info == self.prefix or path_info.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + self.prefix
            new_path = path_info[len(self.prefix):]
            environ["PATH_INFO"] = new_path if new_path.startswith("/") else "/" + new_path
        return self.app(environ, start_response)


class TestWSGIPrefixMiddleware(unittest.TestCase):
    def setUp(self):
        self.flask_app = Flask("test_app")

        @self.flask_app.route("/")
        def index():
            return jsonify({"route": "index", "script_name": request.script_root, "path": request.path})

        @self.flask_app.route("/api/stocks")
        def stocks():
            return jsonify({"route": "stocks", "count": 10})

        self.flask_app.wsgi_app = WSGIPrefixStripMiddleware(self.flask_app.wsgi_app, prefix="/ateam/pilos")
        self.client = self.flask_app.test_client()

    def test_direct_root_request(self):
        """Direct request GET / should succeed."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["route"], "index")

    def test_direct_api_request(self):
        """Direct request GET /api/stocks should succeed."""
        res = self.client.get("/api/stocks")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["route"], "stocks")

    def test_prefixed_root_request(self):
        """Prefixed request GET /ateam/pilos/ should be stripped and succeed."""
        res = self.client.get("/ateam/pilos/")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["route"], "index")

    def test_prefixed_api_request(self):
        """Prefixed request GET /ateam/pilos/api/stocks should be stripped and succeed."""
        res = self.client.get("/ateam/pilos/api/stocks")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["route"], "stocks")


if __name__ == "__main__":
    unittest.main()
