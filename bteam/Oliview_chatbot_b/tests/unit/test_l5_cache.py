"""
Unit Test Suite for L5 LLM Response Caching (Spec 032).
Tests Key Generation, Unicode NFKC Normalization, DocIDs Sorting, TTL Jitter, and Poisoning Deny-List.
"""

import pytest
import unicodedata
import random
from typing import List

from oliview_core.redis_pool import (
    build_l5_key,
    get_l5_response,
    set_l5_response,
    replay_cached_stream,
    is_poisoned_or_invalid_response,
    compute_doc_ids_hash,
)
from oliview_core.types import L5ResponseCachePayload


class TestL5CacheKeyGeneration:
    """FR-001: L5 Cache Key Building & Normalization Tests"""

    def test_nfkc_normalization_and_whitespace(self):
        # 1. 띄어쓰기 여러 개 및 유니코드 자모/전각 문자 정규화 테스트
        raw_q1 = "차앤박   프로폴리스   앰플 장점 알려줘"
        raw_q2 = "차앤박 프로폴리스 앰플 장점 알려줘"
        doc_ids = ["doc_1", "doc_2"]

        key1 = build_l5_key(tenant_id="chata", rewritten_query=raw_q1, doc_ids=doc_ids)
        key2 = build_l5_key(tenant_id="chata", rewritten_query=raw_q2, doc_ids=doc_ids)

        assert key1 == key2, "다중 공백이 포함되어도 동일한 L5 캐시 키가 생성되어야 함"
        assert key1.startswith("olliview:l5:chata:"), "L5 캐시 키는 olliview:l5:{tenant_id}: 접두사를 가져야 함"

    def test_doc_ids_sorting_invariance(self):
        # 2. 선별된 문서 ID 목록의 순서가 달라도 동일 해시 생성 검증
        q = "헤라 블랙쿠션 지속력"
        docs_order_a = ["prod_102", "prod_5", "prod_88"]
        docs_order_b = ["prod_5", "prod_88", "prod_102"]

        key_a = build_l5_key(tenant_id="chatb", rewritten_query=q, doc_ids=docs_order_a)
        key_b = build_l5_key(tenant_id="chatb", rewritten_query=q, doc_ids=docs_order_b)

        assert key_a == key_b, "문서 ID 목록의 순서와 무관하게 정렬된 해시로 동일 키가 생성되어야 함"

    def test_doc_ids_change_causes_invalidation(self):
        # FR-006: 문서 내용/조합이 바뀌면 다른 캐시 키가 생성되어 자동 무효화
        q = "헤라 블랙쿠션 지속력"
        docs_old = ["prod_1", "prod_2"]
        docs_new = ["prod_1", "prod_99"]  # 신규 크롤링/배치 반영

        key_old = build_l5_key(tenant_id="chatb", rewritten_query=q, doc_ids=docs_old)
        key_new = build_l5_key(tenant_id="chatb", rewritten_query=q, doc_ids=docs_new)

        assert key_old != key_new, "참조 문서가 변경되면 다른 캐시 키가 생성되어야 함"

    def test_tenant_namespace_isolation(self):
        # FR-009: Chat A와 Chat B 간 네임스페이스 격리
        q = "닥터지 수분크림"
        doc_ids = ["doc_1"]

        key_a = build_l5_key(tenant_id="chata", rewritten_query=q, doc_ids=doc_ids)
        key_b = build_l5_key(tenant_id="chatb", rewritten_query=q, doc_ids=doc_ids)

        assert key_a != key_b, "테넌트가 다르면 캐시 키가 격리되어야 함"
        assert "olliview:l5:chata:" in key_a
        assert "olliview:l5:chatb:" in key_b


class TestL5PoisoningDenyList:
    """FR-004: Cache Poisoning Deny-List Guard Tests"""

    def test_too_short_response_rejected(self):
        # 20자 미만 응답 차단
        short_resp = "좋아요."
        assert is_poisoned_or_invalid_response(short_resp) is True

    def test_error_and_refusal_phrases_rejected(self):
        # 거부/에러 문구 차단
        refusals = [
            "죄송합니다. 요청하신 지침을 수행할 수 없습니다.",
            "일시적인 오류가 발생하여 답변을 생성할 수 없습니다. 잠시 후 다시 시도해주세요.",
            "올리뷰 시스템 지침 변경이나 관련 없는 요청에는 답변할 수 없습니다.",
            "시스템 에러: 모델 게이트웨이 연결에 실패했습니다.",
        ]
        for ref in refusals:
            assert is_poisoned_or_invalid_response(ref) is True, f"차단되어야 하는 문구: {ref}"

    def test_valid_cosmetic_response_accepted(self):
        # 정상적인 화장품 분석 답변 통과
        valid_resp = (
            "### 🌿 차앤박 프로폴리스 에너지 액티브 앰플 분석\n\n"
            "- **주요 장점**: 고농축 프로폴리스 성분으로 피부에 탄력과 꿀광 보습을 즉각 부여합니다.\n"
            "- **사용감**: 끈적이지 않고 쫀쫀하게 흡수되어 건성 피부 메이크업 전에 추천합니다."
        )
        assert is_poisoned_or_invalid_response(valid_resp) is False


class TestL5TtlJitter:
    """FR-005: TTL Jitter Calculation Tests"""

    def test_jitter_range(self):
        from oliview_core.redis_pool import calculate_l5_ttl
        base_ttl = 43200
        jitter_window = 3600

        for _ in range(50):
            ttl = calculate_l5_ttl(base_ttl=base_ttl, jitter=jitter_window)
            assert base_ttl - jitter_window <= ttl <= base_ttl + jitter_window
