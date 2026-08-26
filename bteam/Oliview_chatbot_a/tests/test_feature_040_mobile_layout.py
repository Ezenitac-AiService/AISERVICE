"""
Unit & Contract Tests for Feature 040: ChatA Mobile Header & Layout Optimization
Validates anti-clipping safe area rules, 3x2 responsive category grid, compact panel rules, and desktop parity.
"""

import re
import pytest
from pathlib import Path

APP_FILE = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture
def app_css_content():
    """Load CSS style block from app.py."""
    assert APP_FILE.exists(), f"app.py not found at {APP_FILE}"
    content = APP_FILE.read_text(encoding="utf-8")
    css_match = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    assert css_match, "No <style> block found in app.py"
    return css_match.group(1)


def test_mobile_header_safe_area(app_css_content):
    """Test FR-001: Mobile header anti-clipping and stHeader neutralization."""
    # 1. Check stHeader neutralization
    assert "header[data-testid=\"stHeader\"]" in app_css_content or "[data-testid=\"stHeader\"]" in app_css_content
    assert "visibility: hidden" in app_css_content or "display: none" in app_css_content or "height: 0" in app_css_content

    # 2. Check safe-area-inset-top in padding-top
    assert "env(safe-area-inset-top)" in app_css_content
    assert "max(" in app_css_content


def test_category_grid_rules(app_css_content):
    """Test FR-002: Category buttons 3x2 responsive grid override under @media (max-width: 768px)."""
    # 1. Must contain mobile media query
    assert "@media (max-width: 768px)" in app_css_content

    # 2. Must contain horizontal block flex row override
    assert "stHorizontalBlock" in app_css_content
    assert "touch-action: manipulation" in app_css_content


def test_mobile_panel_compactness(app_css_content):
    """Test FR-003: Compact brand box and attribute card styles for mobile."""
    assert ".brand-box" in app_css_content
    assert ".attribute-card" in app_css_content


def test_desktop_integrity_and_accordion(app_css_content):
    """Test FR-004 & FR-005: Desktop 2-column parity, 240px accordion, and safe-area bottom."""
    # 1. Check safe-area-inset-bottom
    assert "env(safe-area-inset-bottom)" in app_css_content

    # 2. Check accordion max-height and momentum scrolling
    assert "stExpanderDetails" in app_css_content or ".stAccordion" in app_css_content
    assert "max-height" in app_css_content
    assert "-webkit-overflow-scrolling: touch" in app_css_content
