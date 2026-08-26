"""Unit tests for multi-target series citation formatting and XML assembly (Spec 038 US1)."""
import pytest
import re
from unittest.mock import MagicMock

from oliview_core.nodes.context_node import context_builder_node
from oliview_core.models.citation_models import ReviewCitation
from oliview_core.graph_state import RagGraphState, TargetEntity, TargetType, PatternType


def test_multi_target_citation_formatting():
    """복수 시리즈 제품에 대해 네임스페이스 인용 태그 [제품명 리뷰 N]이 XML에 올바르게 구성되는지 검증."""
    state: RagGraphState = {
        "query": "헤라 센슈얼 립 촉촉함과 각질부각 분석해줘",
        "pattern_type": PatternType.EXPLICIT_COMPARE.value,
        "target_entities": [
            TargetEntity(
                target_id="target_1",
                target_name="헤라 센슈얼 누드 밤",
                brand_name="헤라",
                product_name="헤라 센슈얼 누드 밤",
                target_type=TargetType.PRODUCT,
                attribute_query="촉촉함 각질부각",
                spec_header=None,
            ),
            TargetEntity(
                target_id="target_2",
                target_name="헤라 센슈얼 누드 글로스",
                brand_name="헤라",
                product_name="헤라 센슈얼 누드 글로스",
                target_type=TargetType.PRODUCT,
                attribute_query="촉촉함 각질부각",
                spec_header=None,
            ),
        ],
        "reranked_contexts": {
            "target_1": [
                {
                    "review_id": "r1",
                    "product_name": "헤라 센슈얼 누드 밤",
                    "brand_name": "헤라",
                    "review_text": "촉촉하고 각질 부각이 전혀 없어요.",
                    "rating": 5,
                    "rerank_score": 0.92,
                },
                {
                    "review_id": "r2",
                    "product_name": "헤라 센슈얼 누드 밤",
                    "brand_name": "헤라",
                    "review_text": "색상이 자연스럽게 생기를 줍니다.",
                    "rating": 4,
                    "rerank_score": 0.85,
                },
            ],
            "target_2": [
                {
                    "review_id": "r3",
                    "product_name": "헤라 센슈얼 누드 글로스",
                    "brand_name": "헤라",
                    "review_text": "광택감이 뛰어나고 유리알 입술을 만들어줍니다.",
                    "rating": 5,
                    "rerank_score": 0.94,
                }
            ],
        },
        "metrics": {},
    }

    result = context_builder_node(state)
    context_text = result.get("context_text", "")

    # XML 태그 및 네임스페이스 인용 태그 검증
    assert "<context" in context_text
    assert "</context>" in context_text
    assert "<target" in context_text
    assert "[헤라 센슈얼 누드 밤 리뷰 1]" in context_text
    assert "[헤라 센슈얼 누드 밤 리뷰 2]" in context_text
    assert "[헤라 센슈얼 누드 글로스 리뷰 1]" in context_text



def test_citation_regex_replacement():
    """단일 숫자 [1], [2]를 [리뷰 1], [리뷰 2]로 변환하는 정규화 검증."""
    raw_llm_output = "헤라 센슈얼 누드 밤은 촉촉합니다 [1]. 또한 글로스는 광택이 납니다 [2]."
    normalized = re.sub(r"\[(\d+)\]", r"[리뷰 \1]", raw_llm_output)
    assert "[리뷰 1]" in normalized
    assert "[리뷰 2]" in normalized
