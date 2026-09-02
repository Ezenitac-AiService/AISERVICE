import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, ValidationError

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "specs" / "048-anti-fictional-user-and-citation-fidelity" / "contracts"


def load_schema(filename: str) -> dict:
    path = CONTRACTS_DIR / filename
    assert path.exists(), f"Contract file {filename} does not exist at {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_all_contract_schemas_are_valid_draft202012():
    schemas = [
        "changelog_schema.json",
        "chat_api_contract.json",
        "chat_api_response_contract.json",
        "core_prompt_contract.json",
        "runtime_environment_schema.json",
        "sse_event_contract.json",
        "structured_log_contract.json",
    ]
    for filename in schemas:
        schema = load_schema(filename)
        Draft202012Validator.check_schema(schema)


def test_chat_api_response_contract_answered():
    schema = load_schema("chat_api_response_contract.json")
    validator = Draft202012Validator(schema)

    valid_answered = {
        "request_id": "12345678-1234-5678-1234-567812345678",
        "status": "answered",
        "answer": "브링그린 티트리 세럼의 진정 효과 요약입니다.",
        "k_bound": 1,
        "model_invoked": True,
        "citations": [
            {
                "review_index": 1,
                "review_id": "rev_001",
                "display_quote": "진정 효과 좋은지 모르겠어요",
                "quote_redacted": False,
            }
        ],
        "product_links": [
            {
                "label": "브링그린 티트리 세럼 50ml",
                "url": "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000123456",
                "host_validated": True,
            }
        ],
        "pipeline_stages": [
            {"stage": "search", "status": "completed", "latency_ms": 45},
            {"stage": "rerank", "status": "completed", "latency_ms": 120},
            {"stage": "grounding", "status": "completed", "latency_ms": 30},
            {"stage": "synthesis", "status": "completed", "latency_ms": 850},
        ],
        "error": None,
    }
    validator.validate(valid_answered)

    # Invalid: answered with error object
    invalid_answered = dict(valid_answered)
    invalid_answered["error"] = {"code": "SOME_ERROR", "message": "fail"}
    with pytest.raises(ValidationError):
        validator.validate(invalid_answered)

    # Invalid: answered with k_bound=0
    invalid_k0 = dict(valid_answered)
    invalid_k0["k_bound"] = 0
    with pytest.raises(ValidationError):
        validator.validate(invalid_k0)


def test_chat_api_response_contract_abstained():
    schema = load_schema("chat_api_response_contract.json")
    validator = Draft202012Validator(schema)

    valid_abstained = {
        "request_id": "12345678-1234-5678-1234-567812345678",
        "status": "abstained",
        "answer": "관련 리뷰 정보를 찾을 수 없어 답변이 기권되었습니다.",
        "k_bound": 0,
        "model_invoked": False,
        "citations": [],
        "pipeline_stages": [
            {"stage": "search", "status": "completed", "latency_ms": 40},
            {"stage": "rerank", "status": "skipped", "latency_ms": 0},
            {"stage": "grounding", "status": "skipped", "latency_ms": 0},
            {"stage": "synthesis", "status": "skipped", "latency_ms": 0},
        ],
        "error": None,
    }
    validator.validate(valid_abstained)

    # Invalid: abstained with citations
    invalid_abstained = dict(valid_abstained)
    invalid_abstained["citations"] = [
        {"review_index": 1, "review_id": "rev_1", "display_quote": "q", "quote_redacted": False}
    ]
    with pytest.raises(ValidationError):
        validator.validate(invalid_abstained)


def test_sse_event_contract_all_events():
    schema = load_schema("sse_event_contract.json")
    validator = Draft202012Validator(schema)

    events = [
        {
            "request_id": "12345678-1234-5678-1234-567812345678",
            "event_id": "evt_001",
            "sequence": 0,
            "event": "start",
            "data": {"started_at": "2026-09-02T12:00:00Z"},
        },
        {
            "request_id": "12345678-1234-5678-1234-567812345678",
            "event_id": "evt_002",
            "sequence": 1,
            "event": "delta",
            "data": {"text": "진정 효과에 대한"},
        },
        {
            "request_id": "12345678-1234-5678-1234-567812345678",
            "event_id": "evt_003",
            "sequence": 2,
            "event": "citation",
            "data": {
                "review_index": 1,
                "review_id": "rev_001",
                "display_quote": "진정 효과 좋은지 모르겠어요",
                "quote_redacted": False,
            },
        },
        {
            "request_id": "12345678-1234-5678-1234-567812345678",
            "event_id": "evt_004",
            "sequence": 3,
            "event": "product_link",
            "data": {
                "label": "브링그린 티트리 세럼",
                "url": "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000123456",
                "host_validated": True,
            },
        },
        {
            "request_id": "12345678-1234-5678-1234-567812345678",
            "event_id": "evt_005",
            "sequence": 4,
            "event": "pipeline_stage",
            "data": {"stage": "search", "status": "completed", "latency_ms": 42},
        },
        {
            "request_id": "12345678-1234-5678-1234-567812345678",
            "event_id": "evt_006",
            "sequence": 5,
            "event": "done",
            "data": {
                "status": "answered",
                "k_bound": 1,
                "model_invoked": True,
                "completed_at": "2026-09-02T12:00:02Z",
            },
        },
    ]
    for ev in events:
        validator.validate(ev)


def test_runtime_adapter_conformance_red_gate():
    """RED GATE: Asserts that oliview_core runtime module exports required entities and adapters.
    Fails until Phase 3 implementation connects them."""
    import oliview_core  # type: ignore
    assert hasattr(oliview_core, "ProductLinkCard"), "oliview_core must export ProductLinkCard"
    assert hasattr(oliview_core, "PipelineStageEvent"), "oliview_core must export PipelineStageEvent"
    assert hasattr(oliview_core, "ContextReviewRegistry"), "oliview_core must export ContextReviewRegistry"
    assert hasattr(oliview_core, "StreamingTokenInterceptor"), "oliview_core must export StreamingTokenInterceptor"
    assert hasattr(oliview_core, "GroundednessSanitizer"), "oliview_core must export GroundednessSanitizer"
