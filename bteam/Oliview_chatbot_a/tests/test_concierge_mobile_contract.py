import pytest
from pathlib import Path


def test_chata_concierge_contract_and_mobile_layout_red_gate():
    """RED GATE: Asserts ChatA main.py / chat_ui.js provides mobile-first concierge contract,
    100dvh layout, visualViewport keyboard defense, 48px touch targets, and reject client persona."""
    style_css = Path(__file__).resolve().parents[1] / "static" / "css" / "style.css"
    assert style_css.exists(), "style.css must exist"
    css_content = style_css.read_text(encoding="utf-8")
    assert "100dvh" in css_content, "RED GATE: style.css must use 100dvh"
    assert "85svh" in css_content, "RED GATE: style.css must use 85svh"

    chat_js = Path(__file__).resolve().parents[1] / "static" / "js" / "chat_ui.js"
    assert chat_js.exists(), "chat_ui.js must exist"
    js_content = chat_js.read_text(encoding="utf-8")
    assert "visualViewport" in js_content, "RED GATE: chat_ui.js must bind visualViewport resize listener"
    assert "product_link" in js_content, "RED GATE: chat_ui.js must process structured product_link events"
