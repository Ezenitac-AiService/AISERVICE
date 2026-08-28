# -*- coding: utf-8 -*-
"""
tests/test_verification_report.py
=================================
User Story 7: verification_report.json 스키마 및 11개 엔드포인트 검증 테스트.
"""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from migration_pack.scripts.verify_migration import ENDPOINTS, build_verification_report


def test_endpoints_count_and_keys():
    assert len(ENDPOINTS) == 11
    names = [ep["name"] for ep in ENDPOINTS]
    assert "Nginx Gateway Root" in names
    assert "Model Gateway (LLM)" in names
    assert "BGE-M3 Embedding" in names
    assert "BGE Reranker" in names
    assert "Pilos Web" in names
    assert "Oliview Frontend" in names
    assert "A-Team MySQL (3307)" in names
    assert "B-Team MySQL (3306)" in names



def test_verification_report_structure():
    mock_results = [{
        "name": ep["name"],
        "url": ep["url"],
        "category": ep.get("category", "HTTP"),
        "status": "PASS",
        "status_code": 200,
        "latency_ms": 15.2,
        "message": "OK",
    } for ep in ENDPOINTS]

    report = build_verification_report(mock_results)
    assert report["total_checks"] == 11
    assert report["passed_checks"] == 11
    assert report["failed_checks"] == 0
    assert report["overall_status"] == "HEALTHY"
