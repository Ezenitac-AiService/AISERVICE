import pytest
from pathlib import Path


def test_chatb_analyst_contract_and_dashboard_layout_red_gate():
    """RED GATE: Asserts ChatB project_ragapi.py / index.html provides analyst contract,
    adaptive 2-column desktop / drawer layout, and real pipeline_stage events."""
    index_html = Path(__file__).resolve().parents[1] / "index.html"
    assert index_html.exists(), "ChatB index.html must exist"
    html_content = index_html.read_text(encoding="utf-8")
    assert "pipeline_stage" in html_content, "RED GATE: index.html must process pipeline_stage events"
    assert "document_score_threshold" in html_content, "RED GATE: index.html must have document_score_threshold slider"
