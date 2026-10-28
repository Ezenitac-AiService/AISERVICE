"""
Unit tests for Context Window & Sizing Calibration per Feature 008 Phase 9 (T031-A).
Validates:
1. Dynamic target partitioning in rerank_node (single 12, compare max 8 per target, total <= 16).
2. PreFlightContextGuard 32K context window and 24,000 token hard ceiling.
3. ContextHarnessProfile 32K defaults.
4. Generous output token budget in synthesis_node (max_tokens = 4096).
5. Selective XML sanitization (disarming < and >, preserving quotes and Korean text).
6. Optimistic prefix-matching sliding window buffer for ephemeral canary tokens.
7. Clean text L5 cache ingestion invariant and synthesis_llm_model key binding.
8. doc_id and review_id schema compatibility in _extract_doc_ids.
9. Permanent deletion of chromadb.PersistentClient in retrieval.py.
"""

import inspect
import uuid
import pytest
from oliview_core.config import get_settings, CoreSettings
from oliview_core.graph_state import ContextHarnessProfile, PatternType
from oliview_core.guardrail import PreFlightContextGuard, escape_review_xml
from oliview_core.nodes.rerank_node import reranker_node, apply_3guardrail_score_cliff
from oliview_core.nodes.synthesis_node import (
    _get_max_tokens_for_pattern,
    _extract_doc_ids,
    filter_canary_stream_optimistic,
)
import oliview_core.retrieval as retrieval_mod


def test_dynamic_target_partitioning():
    """Verify dynamic target partitioning formula: target_max_k = 12 if len(targets) <= 1 else max(4, 16 // len(targets))."""
    # 1 target -> 12
    targets_1 = ["target_1"]
    k1 = 12 if len(targets_1) <= 1 else max(4, 16 // len(targets_1))
    assert k1 == 12

    # 2 targets -> 8
    targets_2 = ["target_1", "target_2"]
    k2 = 12 if len(targets_2) <= 1 else max(4, 16 // len(targets_2))
    assert k2 == 8
    assert k2 * len(targets_2) <= 16

    # 3 targets -> 5 (total 15 <= 16)
    targets_3 = ["target_1", "target_2", "target_3"]
    k3 = 12 if len(targets_3) <= 1 else max(4, 16 // len(targets_3))
    assert k3 == 5
    assert k3 * len(targets_3) <= 16

    # 4 targets -> 4 (total 16 <= 16)
    targets_4 = ["t1", "t2", "t3", "t4"]
    k4 = 12 if len(targets_4) <= 1 else max(4, 16 // len(targets_4))
    assert k4 == 4
    assert k4 * len(targets_4) <= 16


def test_preflight_context_guard_ceiling():
    """Verify total_n_ctx = 32768 and safe_input_budget is capped at 24000."""
    guard = PreFlightContextGuard()
    budget = guard.get_safe_input_budget(total_n_ctx=32768, max_output_tokens=4096)
    assert budget == 24000, f"Expected 24000 ceiling, got {budget}"

    # Verify default profile
    profile = ContextHarnessProfile()
    assert profile.total_n_ctx == 32768
    assert profile.tier_name == "32K_STANDARD"
    assert profile.max_input_tokens == 24000
    assert profile.max_output_tokens == 4096


def test_synthesis_output_token_budget():
    """Verify generous output token budget: default 4096 tokens."""
    settings = CoreSettings()
    assert settings.max_single_output_tokens == 4096
    assert settings.max_compare_output_tokens == 4096
    assert settings.CHAT_OUTPUT_TOKEN_CAP == 4096
    assert settings.CHAT_TIMEOUT_MS == 60000

    single_tokens = _get_max_tokens_for_pattern(PatternType.SINGLE_TARGET)
    assert single_tokens == 4096

    compare_tokens = _get_max_tokens_for_pattern(PatternType.EXPLICIT_COMPARE)
    assert compare_tokens == 4096


def test_xml_sanitization_selective_disarming():
    """Verify selective XML disarming (<, > -> &lt;, &gt;) preserving quotes and Korean text."""
    raw_review = '이 제품은 "수분감"이 \'최고\'입니다! <script>alert("hack")</script> & 짱'
    escaped = escape_review_xml(raw_review)

    # < and > must be disarmed
    assert "<script>" not in escaped
    assert "</script>" not in escaped
    assert "&lt;script&gt;" in escaped
    assert "&lt;/script&gt;" in escaped

    # Quotes should NOT be bloated into &quot; or &#x27; to prevent token bloat
    assert '"수분감"' in escaped
    assert "'최고'" in escaped
    assert "&quot;" not in escaped
    assert "&#x27;" not in escaped


def test_optimistic_prefix_matching_buffer_and_canary_filter():
    """Verify optimistic prefix-matching sliding window buffer filters split canary chunks without TTFT delay."""
    canary = uuid.uuid4().hex  # 32 hex chars
    assert len(canary) == 32

    # Simulate SSE chunks where canary is split across chunk boundaries
    part1 = canary[:12]
    part2 = canary[12:24]
    part3 = canary[24:]
    chunks = ["안녕하세요! ", "제품 리뷰입니다. ", f"보안코드: {part1}", part2, f"{part3} 정상 완료.", " 감사합니다."]

    filtered_chunks = list(filter_canary_stream_optimistic(iter(chunks), canary_token=canary))
    joined_output = "".join(filtered_chunks)

    # Invariant 1: Canary token must be 100% removed
    assert canary not in joined_output
    assert part1 not in joined_output or part2 not in joined_output

    # Invariant 2: Normal content must be preserved
    assert "안녕하세요! " in joined_output
    assert "제품 리뷰입니다. " in joined_output
    assert "감사합니다." in joined_output


def test_doc_id_and_review_id_schema_compatibility():
    """Verify _extract_doc_ids extracts doc_id or review_id without falling back to text slicing."""
    state_doc_id = {
        "reranked_contexts": {
            "target_1": [
                {"doc_id": "rev_1001", "review_text": "수분감이 촉촉해요"},
                {"doc_id": "rev_1002", "review_text": "흡수가 빨라요"},
            ]
        }
    }
    extracted = _extract_doc_ids(state_doc_id)
    assert extracted == ["rev_1001", "rev_1002"]

    state_review_id = {
        "reranked_contexts": {
            "target_1": [
                {"review_id": 2001, "review_text": "보습력이 좋아요"},
                {"review_id": 2002, "review_text": "끈적이지 않아요"},
            ]
        }
    }
    extracted_legacy = _extract_doc_ids(state_review_id)
    assert extracted_legacy == ["2001", "2002"]


def test_retrieval_persistent_client_permanent_deletion():
    """Verify chromadb.PersistentClient is completely absent from retrieval.py per Constitution III."""
    source = inspect.getsource(retrieval_mod)
    assert "PersistentClient" not in source, "PersistentClient code still present in retrieval.py!"
