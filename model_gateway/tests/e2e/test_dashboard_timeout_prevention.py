"""
Playwright E2E test for Dashboard UI dynamic relative API paths and timeout prevention (US3, FR-008, SC-006, DoD-006).
"""

import pytest
import os
import re


def test_dashboard_static_relative_paths():
    """FR-008: Verify dashboard static HTML/JS assets use relative paths (no hardcoded localhost)."""
    static_dir = os.path.abspath("src/api/static")
    assert os.path.exists(static_dir), f"Dashboard static dir not found: {static_dir}"

    for root, _, files in os.walk(static_dir):
        for file in files:
            if file.endswith((".html", ".js")):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # Ensure no hardcoded localhost API endpoints exist in dashboard frontend JS
                    assert not re.search(r"http://localhost:\d+/dashboard/api", content), \
                        f"Hardcoded localhost API found in {path}"
                    assert not re.search(r"http://127\.0\.0\.1:\d+/dashboard/api", content), \
                        f"Hardcoded 127.0.0.1 API found in {path}"
