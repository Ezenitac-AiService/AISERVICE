"""
Unit Test Suite for User Story 2 (Spec 032):
RAG Context Invalidation & Multi-turn Rewritten Query Integrity.
"""

import pytest
from oliview_core.redis_pool import build_l5_key, compute_doc_ids_hash


def test_multiturn_anaphora_rewritten_query_isolation():
    """
    US2: '그거 얼마야?' 질의가 1턴 제품('헤라 쿠션')에 의해 '헤라 블랙쿠션 얼마야?'로 복원되었을 때,
    다른 제품('롬앤 틴트 얼마야?')의 캐시와 격리됨을 검증.
    """
    q_turn1_resolved = "헤라 블랙쿠션 얼마야"
    q_turn2_different = "롬앤 쥬시래스팅 틴트 얼마야"
    doc_ids_hera = ["hera_101", "hera_102"]
    doc_ids_romand = ["romand_201", "romand_202"]

    key_hera = build_l5_key(tenant_id="chatb", rewritten_query=q_turn1_resolved, doc_ids=doc_ids_hera)
    key_romand = build_l5_key(tenant_id="chatb", rewritten_query=q_turn2_different, doc_ids=doc_ids_romand)

    assert key_hera != key_romand, "복원된 대명사 질의는 대상 제품별로 독립된 캐시 키를 가져야 함"


def test_rag_crawler_update_invalidation():
    """
    US2: 새벽 크롤링/감정 분석 배치로 인해 Top-K 리뷰 문서 조합이 변경되었을 때,
    기존 캐시가 자동 무효화(새로운 캐시 키 생성)됨을 검증.
    """
    q = "차앤박 프로폴리스 앰플 장점"
    doc_ids_yesterday = ["cnp_01", "cnp_02", "cnp_03"]
    doc_ids_today = ["cnp_01", "cnp_02", "cnp_99"]  # 신규 베스트 리뷰 반영

    key_yesterday = build_l5_key(tenant_id="chata", rewritten_query=q, doc_ids=doc_ids_yesterday)
    key_today = build_l5_key(tenant_id="chata", rewritten_query=q, doc_ids=doc_ids_today)

    assert key_yesterday != key_today, "선별된 상위 리뷰가 달라지면 캐시 키가 달라져 캐시 미스가 발생해야 함"
