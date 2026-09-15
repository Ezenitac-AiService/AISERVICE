"""
Unit & Integration Test for ChatA Static Assets Routing (Spec 005 / US1).
Verifies that Starlette mounts correctly serve static assets under both subpath
and stripped prefix paths, preventing 404 layout breakage.
"""

import unittest
import sys
import os

# Add ChatA root to path
CHATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if CHATA_DIR not in sys.path:
    sys.path.insert(0, CHATA_DIR)

from starlette.testclient import TestClient
from main import app


class TestChatAStaticRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_chata_index_page(self):
        """Verify index.html is served with base href."""
        resp = self.client.get("/bteam/chata/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('<base href="/bteam/chata/">', resp.text)

    def test_chata_static_css_under_prefix(self):
        """Verify CSS assets load with 200 OK when requested with subpath prefix."""
        resp = self.client.get("/bteam/chata/static/css/style.css")
        self.assertEqual(resp.status_code, 200, f"Expected 200 but got {resp.status_code}: {resp.text}")
        self.assertIn("text/css", resp.headers.get("content-type", ""))
        self.assertGreater(len(resp.content), 100)

    def test_chata_static_mobile_css_under_prefix(self):
        """Verify mobile CSS loads with 200 OK."""
        resp = self.client.get("/bteam/chata/static/css/mobile.css")
        self.assertEqual(resp.status_code, 200)

    def test_chata_static_js_under_prefix(self):
        """Verify JS assets load with 200 OK when requested with subpath prefix."""
        resp = self.client.get("/bteam/chata/static/js/app.js")
        self.assertEqual(resp.status_code, 200)

        resp2 = self.client.get("/bteam/chata/static/js/chat_ui.js")
        self.assertEqual(resp2.status_code, 200)

    def test_direct_static_css_fallback(self):
        """Verify direct /static path also works (dual normalization)."""
        resp = self.client.get("/static/css/style.css")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
