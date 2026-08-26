"""Contract tests for 2026 Mobile Responsive Web and Bottom Sheet Drawer (Spec 038 US4)."""
import pytest
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def test_index_html_viewport_and_drawer_structure():
    """index.html 내 모바일 viewport 메타 태그 및 바텀 시트 구조 검증."""
    index_file = STATIC_DIR / "index.html"
    assert index_file.exists(), "index.html must exist in static/"
    content = index_file.read_text(encoding="utf-8")

    # Viewport fit cover for notch/safe-area
    assert "viewport-fit=cover" in content
    assert "name=\"viewport\"" in content

    # Mobile CSS inclusion
    assert "/static/css/mobile.css" in content

    # Bottom sheet structure
    assert "bottom-sheet-overlay" in content
    assert "bottom-sheet-drawer" in content
    assert "bottom-sheet-handle" in content


def test_mobile_css_breakpoints_and_safe_area():
    """mobile.css 내 768px 미디어 쿼리 및 Safe-Area 대응 검증."""
    mobile_css = STATIC_DIR / "css" / "mobile.css"
    assert mobile_css.exists(), "mobile.css must exist in static/css/"
    content = mobile_css.read_text(encoding="utf-8")

    # Responsive breakpoint
    assert "@media (max-width: 768px)" in content

    # Safe-Area Inset
    assert "safe-area-inset-bottom" in content

    # Bottom sheet transition & transform
    assert ".bottom-sheet-drawer" in content
    assert "transform: translateY(100%)" in content or "transform" in content


def test_chat_ui_js_bottom_sheet_functions():
    """chat_ui.js 내 바텀 시트 열기/닫기 및 인라인 뱃지 렌더링 검증."""
    chat_ui_js = STATIC_DIR / "js" / "chat_ui.js"
    assert chat_ui_js.exists(), "chat_ui.js must exist in static/js/"
    content = chat_ui_js.read_text(encoding="utf-8")

    # Bottom Sheet functions
    assert "openBottomSheet" in content
    assert "closeBottomSheet" in content
    assert "handleCitationClick" in content

    # Citation badge rendering
    assert "citation-badge" in content
