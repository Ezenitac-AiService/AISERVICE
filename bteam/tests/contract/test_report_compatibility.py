import copy
import json
from pathlib import Path

import pytest
from oliview_core.reports import validate_report

ROOT = Path(__file__).resolve().parents[2]


def test_grounded_report_requires_real_review_citations():
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "citation_fixture.json").read_text(
            encoding="utf-8"
        )
    )
    validate_report(
        fixture["grounded"],
        reviews={7: {"product_id": 2, "review_content": "커버력이 좋아요"}},
    )


def test_uncited_or_cross_product_claim_is_rejected():
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "citation_fixture.json").read_text(
            encoding="utf-8"
        )
    )
    bad = copy.deepcopy(fixture["grounded"])
    bad["claims"][0]["citations"][0]["source_review_id"] = 99
    with pytest.raises(ValueError):
        validate_report(
            bad, reviews={7: {"product_id": 2, "review_content": "커버력이 좋아요"}}
        )
