from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.performance
def test_performance_fixture_has_warmup_and_general_query_mix():
    rows = [
        json.loads(line)
        for line in (ROOT / "tests" / "fixtures" / "performance_queries.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert len(rows) == 100
    assert sum(row["class"] == "zero-search" for row in rows) == 20
    assert sum(row["class"] == "general" for row in rows) == 80
    assert all(row.get("input_token_cap", 256) == 256 for row in rows)
    assert all(row.get("output_token_cap", 512) == 512 for row in rows)
