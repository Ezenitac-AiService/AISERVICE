from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def evaluate_smoke_probe(
    endpoints_status: dict[str, int],
    zero_search_responses: list[dict[str, Any]],
) -> dict[str, Any]:
    """컷오버 직후 스모크 테스트 결과를 판정합니다."""
    failed_endpoints = {k: v for k, v in endpoints_status.items() if v != 200}
    if failed_endpoints:
        return {
            "status": "FAILED",
            "reason": f"엔드포인트 비정상 응답: {failed_endpoints}",
            "http_5xx_count": sum(1 for v in endpoints_status.values() if v >= 500),
        }

    for resp in zero_search_responses:
        if (
            resp.get("status") not in ("NO_REVIEWS", "GROUNDING_FAILED", "SUCCESS_EMPTY")
            and not resp.get("abstention", False)
            and resp.get("reviews_count", 0) == 0
        ):
            return {
                "status": "FAILED",
                "reason": f"Zero-search 환각 의심 응답: {resp}",
                "http_5xx_count": 0,
            }

    return {
        "status": "PASSED",
        "endpoints_checked": len(endpoints_status),
        "zero_search_checked": len(zero_search_responses),
        "http_5xx_count": 0,
    }


def test_post_cutover_smoke_success():
    endpoints = {
        "/bteam/oliview/api/health": 200,
        "/bteam/oliview/": 200,
        "/bteam/chata/": 200,
        "/bteam/chatb/": 200,
    }
    zero_search_resps = [
        {"query": "존재하지 않는 제품", "status": "NO_REVIEWS", "abstention": True, "reviews_count": 0},
        {"query": "검색 결과 없는 속성", "status": "GROUNDING_FAILED", "abstention": True, "reviews_count": 0},
    ]

    result = evaluate_smoke_probe(endpoints, zero_search_resps)
    assert result["status"] == "PASSED"
    assert result["http_5xx_count"] == 0


def test_post_cutover_smoke_5xx_failure():
    endpoints = {
        "/bteam/oliview/api/health": 502,
        "/bteam/oliview/": 200,
        "/bteam/chata/": 200,
        "/bteam/chatb/": 200,
    }
    result = evaluate_smoke_probe(endpoints, [])
    assert result["status"] == "FAILED"
    assert result["http_5xx_count"] == 1


def test_post_cutover_smoke_hallucination_detected():
    endpoints = {
        "/bteam/oliview/api/health": 200,
        "/bteam/oliview/": 200,
        "/bteam/chata/": 200,
        "/bteam/chatb/": 200,
    }
    zero_search_resps = [
        {"query": "존재하지 않는 제품", "status": "GENERATED", "abstention": False, "reviews_count": 0}
    ]
    result = evaluate_smoke_probe(endpoints, zero_search_resps)
    assert result["status"] == "FAILED"
