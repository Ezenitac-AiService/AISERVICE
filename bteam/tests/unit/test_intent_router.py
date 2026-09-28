"""
Unit tests for Kiwipiepy 2-Pass Morphological Intent Router and Entity Normalizer.
Validates:
1. Conjunction particle (JC: 과/와/하고/이랑) between nouns (e.g. '수분감과 흡수력') is NOT misclassified as comparison.
2. True comparisons (2+ products or comparison predicates like '비교', '차이점', 'vs') trigger EXPLICIT_COMPARE.
3. Attribute inquiries preserve single target entity and product name.
Feature: 008-bteam-rag-refactor (T009)
"""

import pytest
from oliview_core.graph_state import RagGraphState, PatternType
from oliview_core.nodes.router_node import intent_router_node
from oliview_core.utils.entity_normalizer import HybridEntityNormalizer, QueryIntentEnum


@pytest.fixture
def normalizer():
    return HybridEntityNormalizer()


def test_conjunction_aspect_not_misclassified_as_comparison(normalizer):
    """
    '차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘'
    '수분감과' contains conjunction particle (JC '과'), linking two aspects.
    It must NOT trigger comparison intent.
    """
    query = "차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘"
    res = normalizer.normalize(query)

    # Intent must NOT be COMPARISON
    assert res.intent != QueryIntentEnum.COMPARISON

    # Aspects must be extracted
    assert "수분감" in res.extracted_aspects
    assert "흡수력" in res.extracted_aspects

    # Brand must be preserved as CNP / 차앤박
    assert res.extracted_brand in ("CNP", "차앤박")


def test_intent_router_node_single_target_aspect_query():
    """
    Verify intent_router_node correctly routes '차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘'.
    Pattern must be ASPECT_PROS_CONS or SINGLE_TARGET, NOT EXPLICIT_COMPARE.
    Target product name must be preserved (not dropped to None).
    """
    query = "차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘"
    state: RagGraphState = {
        "trace_id": "test_trace_001",
        "query": query,
    }

    result = intent_router_node(state)
    pattern = result.get("pattern_type")
    assert pattern in (PatternType.ASPECT_PROS_CONS.value, PatternType.SINGLE_TARGET.value)
    assert pattern != PatternType.EXPLICIT_COMPARE.value

    targets = result.get("target_entities", [])
    assert len(targets) == 1
    t0 = targets[0]
    assert "프로폴리스" in t0["target_name"] or "앰플" in t0["target_name"] or "차앤박" in t0["target_name"]
    # Product name or target name must be non-empty and preserved
    assert t0.get("product_name") or t0.get("target_name")


def test_true_comparison_query_classified_as_explicit_compare(normalizer):
    """
    True comparison query with 2 products or comparative predicate '비교'.
    '헤라 블랙쿠션이랑 클리오 킬커버 비교해줘' -> COMPARISON
    """
    query = "헤라 블랙쿠션이랑 클리오 킬커버 비교해줘"
    res = normalizer.normalize(query)
    assert res.intent == QueryIntentEnum.COMPARISON

    state: RagGraphState = {
        "trace_id": "test_trace_002",
        "query": query,
    }
    result = intent_router_node(state)
    assert result.get("pattern_type") == PatternType.EXPLICIT_COMPARE.value
    targets = result.get("target_entities", [])
    assert len(targets) >= 2


def test_kiwi_tokenize_called_in_fast_path(mocker, normalizer):
    """
    T025-A Red Gate:
    Verify that self._kiwi.tokenize() is actually invoked during _fast_path_normalize().
    Inspect tokenized POS tags to assert that Kiwi morphology tokenization occurred.
    """
    assert normalizer._kiwi is not None, "Kiwi instance is not initialized"
    spy = mocker.spy(normalizer._kiwi, "tokenize")
    query = "차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘"
    res = normalizer.normalize(query)

    # Kiwi tokenize must be invoked in fast-path
    assert spy.call_count >= 1, "self._kiwi.tokenize() was never called in _fast_path_normalize"

    # Tokenized POS output inspection
    tokens = spy.spy_return
    assert tokens is not None
    token_pairs = [(t.form, t.tag) for t in tokens]
    # Conjunction particle JC ('과') connecting two noun aspects must be identified
    assert ("과", "JC") in token_pairs
    assert any(form == "수분감" for form, tag in token_pairs)
    assert any(form == "흡수력" for form, tag in token_pairs)


def test_kiwi_distinguishes_jc_conjunction_vs_jkb_adverbial(mocker, normalizer):
    """
    T025-A Red Gate:
    Verify conjunction particle (JC: 과/와/랑) vs adverbial particle (JKB: 로/에/에서).
    Coordinated aspects ([Aspect] + JC + [Aspect]) must preserve SINGLE_TARGET / ASPECT_PROS_CONS
    and extract both aspects without triggering COMPARISON intent.
    Adverbial particle (JKB) queries like '...앰플로 수분감 알려줘' must also preserve SINGLE_TARGET.
    """
    assert normalizer._kiwi is not None, "Kiwi instance is not initialized"
    spy = mocker.spy(normalizer._kiwi, "tokenize")

    # 1. Conjunction particle (JC) query
    query_jc = "차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘"
    res_jc = normalizer.normalize(query_jc)
    assert spy.call_count >= 1
    tokens_jc = [(t.form, t.tag) for t in spy.spy_return]
    assert ("과", "JC") in tokens_jc
    assert res_jc.intent != QueryIntentEnum.COMPARISON
    assert "수분감" in res_jc.extracted_aspects
    assert "흡수력" in res_jc.extracted_aspects

    # 2. Adverbial particle (JKB) query
    spy.reset_mock()
    query_jkb = "차앤박 프로폴리스 앰플로 수분감 알려줘"
    res_jkb = normalizer.normalize(query_jkb)
    assert spy.call_count >= 1
    tokens_jkb = [(t.form, t.tag) for t in spy.spy_return]
    # JKB present for '로', no JC
    assert any(tag == "JKB" for form, tag in tokens_jkb)
    assert not any(tag == "JC" for form, tag in tokens_jkb)
    assert res_jkb.intent != QueryIntentEnum.COMPARISON
    assert "수분감" in res_jkb.extracted_aspects

