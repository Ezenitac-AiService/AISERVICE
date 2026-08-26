"""Unit Tests for LangGraph Typed Tools (Spec 037 US1)."""
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oliview_core.tools.search_tools import tool_search_catalog, tool_get_reviews
from oliview_core.tools.spec_tools import tool_get_specs


class TestLangGraphTools(unittest.TestCase):

    def test_tool_search_catalog_interface(self):
        res = tool_search_catalog("틴트", category="립틴트", limit=3)
        self.assertIsInstance(res, list)

    def test_tool_get_specs_interface(self):
        res = tool_get_specs("컬러그램 탕후루 탱글 꿀로스")
        self.assertTrue(res is None or isinstance(res, dict))


if __name__ == "__main__":
    unittest.main()
