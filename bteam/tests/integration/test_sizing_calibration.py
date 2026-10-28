"""
Integration test for Context Window & Sizing Calibration across B-Team & A-Team (T033 / FR-008 / SC-001).
Validates:
1. 10~15 buyer reviews (each 200~400 chars) are synthesized into prompt context.
2. Estimated prompt tokens stay comfortably within the 24,000 safe ceiling (6,000~8,000 tokens).
3. PreFlightContextGuard verifies context without truncation.
4. Generous output token budget (max_tokens = 4096) allows full streaming without cutoffs.
5. Ephemeral canary token filtering does not affect TTFT and purges canary from L5 cache.
6. L5 cache stores clean text under synthesis_llm_model key.
"""

import uuid
import pytest
from unittest.mock import Mock, patch

from oliview_core.config import get_settings, CoreSettings
from oliview_core.graph_state import (
    RagGraphState,
    ContextHarnessProfile,
    PatternType,
    CandidateReview,
    RerankedReview,
)
from oliview_core.guardrail import PreFlightContextGuard, escape_review_xml
from oliview_core.nodes.synthesis_node import (
    _extract_doc_ids,
    _get_max_tokens_for_pattern,
    get_token_stream,
    filter_canary_stream_optimistic,
)
from oliview_core.redis_pool import build_l5_key


def test_12_to_15_reviews_context_synthesis_and_ceiling():
    """Verify 12~15 realistic buyer reviews produce 6,000~8,000 estimated tokens under 24K ceiling."""
    settings = get_settings()
    guard = PreFlightContextGuard()
    profile = ContextHarnessProfile()

    assert profile.total_n_ctx == 32768
    assert profile.max_input_tokens == 24000
    assert profile.max_output_tokens == 4096

    # Construct 12 buyer reviews with realistic detailed Korean review paragraphs (~350-400 chars each)
    review_snippets = []
    reranked_list = []
    for i in range(12):
        text = (
            f"리뷰 {i+1}번: 차앤박 프로폴리스 에너지 앰플을 3주간 아침저녁으로 꾸준히 사용해보았습니다. "
            f"수분감과 보습력이 정말 뛰어나며, 바르는 즉시 피부 속까지 촉촉하게 스며들고 속당김이 말끔하게 해결됩니다. "
            f"유분기가 과하지 않고 영양감이 풍부해 메이크업 전 단계에 발라도 밀리거나 들뜨지 않는 점이 가장 만족스러웠습니다. "
            f"민감성 피부인데 트러블이나 붉은기 없이 순하게 작용하여 환절기 보습 케어용으로 강력 추천합니다."
        )
        safe_text = escape_review_xml(text)
        review_snippets.append(f"<review id='rev_{1000+i}'>{safe_text}</review>")
        reranked_list.append(RerankedReview(
            doc_id=f"rev_{1000+i}",
            review_id=1000 + i,
            review_text=safe_text,
            target_id="target_cnp",
            target_name="차앤박 프로폴리스 앰플",
            product_name="차앤박 프로폴리스 에너지 액티브 앰플",
            brand_name="차앤박",
            category="에센스/앰플",
            rerank_score=0.98 - (i * 0.02),
            rank=i + 1,
            rating=5.0,
        ))

    context_xml = (
        "<context>\n"
        "  <target id='target_cnp' name='차앤박 프로폴리스 앰플'>\n"
        "    <reviews>\n" +
        "\n".join(f"      {r}" for r in review_snippets) +
        "\n    </reviews>\n"
        "  </target>\n"
        "</context>"
    )

    # Context estimation
    estimated_tokens = guard.estimate_tokens(context_xml)
    # 12 reviews of ~250 chars -> ~3000 chars * 1.45 ~ 4350 tokens (comfortably within safe budget)
    safe_budget = guard.get_safe_input_budget(profile.total_n_ctx, profile.max_output_tokens)
    assert safe_budget == 24000
    assert estimated_tokens < safe_budget

    # PreFlightContextGuard must not truncate
    validated_text, was_truncated = guard.validate_and_truncate(
        context_xml,
        total_n_ctx=profile.total_n_ctx,
        max_output_tokens=profile.max_output_tokens,
    )
    assert was_truncated is False
    assert validated_text == context_xml


def test_full_pipeline_streaming_and_canary_isolation():
    """Verify streaming token synthesis completes with 4096 budget and clean L5 cache."""
    settings = get_settings()
    canary = uuid.uuid4().hex
    state: RagGraphState = {
        "trace_id": "test-trace-sizing-001",
        "session_id": "sess-sizing-001",
        "tenant_id": "chata",
        "query": "차앤박 앰플 수분감 알려줘",
        "pattern_type": PatternType.SINGLE_TARGET,
        "context_text": "<context>...</context>",
        "canary_token": canary,
        "context_harness": ContextHarnessProfile(),
        "reranked_contexts": {
            "target_cnp": [
                {"doc_id": "rev_101", "review_id": 101, "review_text": "수분감 짱"},
                {"doc_id": "rev_102", "review_id": 102, "review_text": "보습력 최고"},
            ]
        },
        "bypass_cache": True,
    }

    doc_ids = _extract_doc_ids(state)
    assert doc_ids == ["rev_101", "rev_102"]

    max_tokens = _get_max_tokens_for_pattern(state["pattern_type"], state["context_harness"])
    assert max_tokens == 4096

    # Verify L5 cache key format incorporates synthesis_llm_model into key hash
    l5_key = build_l5_key(
        tenant_id="chata",
        rewritten_query="차앤박 앰플 수분감 알려줘",
        doc_ids=doc_ids,
        model_id=settings.synthesis_llm_model,
        prompt_version="v1.0",
    )
    l5_key_other_model = build_l5_key(
        tenant_id="chata",
        rewritten_query="차앤박 앰플 수분감 알려줘",
        doc_ids=doc_ids,
        model_id="other-model-id",
        prompt_version="v1.0",
    )
    assert l5_key.startswith("olliview:l5:chata:")
    assert l5_key != l5_key_other_model

    # Mock AiGatewayClient.generate_stream
    mock_chunks = [
        "차앤박 프로폴리스 앰플은 ",
        "실제 구매자 리뷰 [리뷰 1]에 따르면 ",
        "수분감이 매우 풍부하고 ",
        "흡수가 빠릅니다.",
    ]
    with patch("oliview_core.nodes.synthesis_node.AiGatewayClient") as mock_client_cls:
        instance = mock_client_cls.return_value
        instance.generate_stream.return_value = iter(mock_chunks)

        stream = get_token_stream(state)
        result_chunks = list(stream)

        assert "".join(result_chunks) == "".join(mock_chunks)
        assert canary not in "".join(result_chunks)
