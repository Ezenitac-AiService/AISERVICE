"""
Unit tests for Implicit Anaphora Resolution & Redis On-Demand Deep Recall (Spec 035 T006).
"""

import pytest
from oliview_core.graph_state import AnaphoraTurnTag, DeepRecallTurnPayload
from oliview_core.anaphora_resolver import AnaphoraResolver


def test_anaphora_resolution_exact_entity_match():
    turn_tags = [
        AnaphoraTurnTag(
            turn_index=3,
            entities_mentioned=["차앤박 프로폴리스 에너지 앰플"],
            attributes_discussed=["보습", "영양", "25000원"],
            short_summary="차앤박 앰플의 보습력과 가격대를 안내함"
        ),
        AnaphoraTurnTag(
            turn_index=7,
            entities_mentioned=["닥터지 레드 블레미쉬 크림"],
            attributes_discussed=["진정", "수분", "여드름성 피부"],
            short_summary="닥터지 수분크림의 진정 성분과 수분감을 비교 분석함"
        )
    ]
    resolver = AnaphoraResolver()
    
    # Query mentions "그 크림" -> should match Turn 7 (닥터지 레드 블레미쉬 크림)
    detected_turn = resolver.resolve_turn_from_tags("아까 말한 그 크림 성분이 어때?", turn_tags)
    assert detected_turn == 7

    # Query mentions "앰플" -> should match Turn 3
    detected_turn = resolver.resolve_turn_from_tags("처음에 비교했던 앰플 가격이 얼마였지?", turn_tags)
    assert detected_turn == 3


def test_anaphora_no_match():
    turn_tags = [
        AnaphoraTurnTag(
            turn_index=1,
            entities_mentioned=["이니스프리 그린티 세럼"],
            attributes_discussed=["수분"],
            short_summary="이니스프리 세럼 설명"
        )
    ]
    resolver = AnaphoraResolver()
    # Brand new query without anaphora
    detected_turn = resolver.resolve_turn_from_tags("라운드랩 독도 토너 알려줘", turn_tags)
    assert detected_turn is None
