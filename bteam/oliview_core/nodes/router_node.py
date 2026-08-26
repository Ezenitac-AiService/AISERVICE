"""
Intent Router Node (Spec 030 FR-002 / FR-015).
사용자 질의의 의도를 분류하고 분석 대상 엔티티를 추출/검증하는 LangGraph 노드.
3대 질의 패턴 라우팅: EXPLICIT_COMPARE, FEATURE_DISCOVERY, ASPECT_PROS_CONS, SINGLE_TARGET.
"""

import re
import time
from typing import Dict, Any, List, Optional

from ..config import get_settings
from ..graph_state import (
    RagGraphState, TargetEntity, PatternType, TargetType,
)
from ..alias_dictionary import normalize_query_brands, resolve_brand_alias
from ..anaphora_resolver import anaphora_resolver
from ..sanitizer import detect_brand_and_category
from ..logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.node.router")

# ──────────────────────────────────────────────────────────────────────────────
# Pattern Detection Regex
# ──────────────────────────────────────────────────────────────────────────────

# 명시적 비교 키워드
_RE_COMPARE = re.compile(
    r"(?:비교|대비|차이|어떤\s*게?\s*(?:더|나아)|vs|versus|맞짱|대결)",
    re.IGNORECASE,
)

# 기능/효과 기반 다자 비교 키워드
_RE_FEATURE_DISCOVERY = re.compile(
    r"(?:좋은|추천|인기|핫한|잘\s*팔리는|유명한)\s*(?:제품|앰플|크림|토너|세럼|마스크|스킨|로션).*(?:비교|추천|알려|골라)",
    re.IGNORECASE,
)

# 장단점/다중 속성 분석 키워드
_RE_ASPECT_PROS_CONS = re.compile(
    r"(?:장단점|장점|단점|좋은\s*점|나쁜\s*점|주의\s*점|솔직|객관|리얼|진짜|후기|분석)",
    re.IGNORECASE,
)

# 이 + 저 (두 제품 나열) 패턴
_RE_TWO_PRODUCTS = re.compile(
    r"(?:이랑|랑|하고|과|와|vs|,)\s*",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Intent Router Node
# ──────────────────────────────────────────────────────────────────────────────

def intent_router_node(state: RagGraphState) -> Dict[str, Any]:
    """
    LangGraph 의도 분류 및 엔티티 추출 노드.

    1. 브랜드/제품 별칭 정규화
    2. 패턴 분류 (3+1 패턴)
    3. 타겟 엔티티 추출 및 검증
    4. 엔티티 유효성 게이트 (FR-015)
    """
    trace_id = state.get("trace_id", get_trace_id())
    query = state.get("query", "")
    settings = get_settings()

    with StepTimer("INTENT", trace_id=trace_id):
        # 0. 대명사 해소 (FR-021: "그거", "전자", "후자" 자동 복원)
        session_id = state.get("session_id", "")
        if session_id:
            resolved_query, resolved_entities = anaphora_resolver.resolve(query, session_id)
            if resolved_entities:
                query = resolved_query
                logger.info(
                    f"대명사 해소: {resolved_entities}",
                    extra={"trace_id": trace_id, "step_id": "INTENT"},
                )

        # 1. 브랜드/제품 별칭 정규화
        normalized_query, detected_brands = normalize_query_brands(query)

        # 2. 패턴 분류
        pattern_type = _classify_pattern(normalized_query, detected_brands)

        # 3. 타겟 엔티티 추출
        target_entities = _extract_targets(
            normalized_query, detected_brands, pattern_type, settings.max_targets
        )

        # 4. 엔티티 유효성 게이트 — 타겟 0건이면 단일 타겟으로 폴백
        if not target_entities:
            brand, _ = detect_brand_and_category(normalized_query)
            target_entities = [
                TargetEntity(
                    target_id="target_1",
                    target_name=brand or normalized_query[:30],
                    brand_name=brand,
                    product_name=None,
                    target_type=TargetType.PRODUCT,
                    attribute_query=None,
                    spec_header=None,
                )
            ]
            pattern_type = PatternType.SINGLE_TARGET

        logger.info(
            f"의도 분류 완료: {pattern_type.value}, 타겟 {len(target_entities)}건",
            extra={
                "trace_id": trace_id,
                "step_id": "INTENT",
                "doc_count": len(target_entities),
            },
        )

    return {
        "normalized_query": normalized_query,
        "rewritten_query": normalized_query,
        "pattern_type": pattern_type.value,
        "target_entities": target_entities,
    }


def _classify_pattern(query: str, brands: List[str]) -> PatternType:
    """질의 텍스트와 감지된 브랜드 수로 패턴을 분류합니다."""
    has_compare = bool(_RE_COMPARE.search(query))
    has_feature = bool(_RE_FEATURE_DISCOVERY.search(query))
    has_aspect = bool(_RE_ASPECT_PROS_CONS.search(query))

    # 2개 이상 브랜드 + 비교 키워드 → 명시적 비교
    if len(brands) >= 2 and has_compare:
        return PatternType.EXPLICIT_COMPARE

    # 2개 이상 브랜드 (비교 키워드 없어도 나열되어 있으면)
    if len(brands) >= 2:
        return PatternType.EXPLICIT_COMPARE

    # 기능/효과 키워드 + 비교/추천
    if has_feature:
        return PatternType.FEATURE_DISCOVERY

    # 장단점/다중 속성 키워드
    if has_aspect:
        return PatternType.ASPECT_PROS_CONS

    return PatternType.SINGLE_TARGET


def _extract_targets(
    query: str,
    brands: List[str],
    pattern: PatternType,
    max_targets: int,
) -> List[TargetEntity]:
    """감지된 브랜드 및 패턴에 따라 타겟 엔티티 목록을 생성합니다."""
    targets: List[TargetEntity] = []

    if pattern == PatternType.EXPLICIT_COMPARE:
        for idx, brand in enumerate(brands[:max_targets]):
            targets.append(TargetEntity(
                target_id=f"target_{idx + 1}",
                target_name=brand,
                brand_name=brand,
                product_name=None,
                target_type=TargetType.PRODUCT,
                attribute_query=_extract_attribute(query),
                spec_header=None,
            ))

    elif pattern == PatternType.FEATURE_DISCOVERY:
        # 기능 기반 질의 — 타겟은 후속 retrieval 노드에서 DB 기반 자동 선별
        targets.append(TargetEntity(
            target_id="discovery_pool",
            target_name=query[:50],
            brand_name=None,
            product_name=None,
            target_type=TargetType.ATTRIBUTE,
            attribute_query=_extract_attribute(query),
            spec_header=None,
        ))

    elif pattern == PatternType.ASPECT_PROS_CONS:
        brand = brands[0] if brands else None
        targets.append(TargetEntity(
            target_id="target_1",
            target_name=brand or query[:30],
            brand_name=brand,
            product_name=None,
            target_type=TargetType.PRODUCT,
            attribute_query=_extract_attribute(query),
            spec_header=None,
        ))

    else:  # SINGLE_TARGET
        brand = brands[0] if brands else None
        if brand:
            targets.append(TargetEntity(
                target_id="target_1",
                target_name=brand,
                brand_name=brand,
                product_name=None,
                target_type=TargetType.PRODUCT,
                attribute_query=_extract_attribute(query),
                spec_header=None,
            ))

    return targets


def _extract_attribute(query: str) -> Optional[str]:
    """질의에서 속성 키워드(수분감, 발림성 등)를 추출합니다."""
    attributes = [
        "수분감", "발림성", "자극성", "흡수력", "지속력", "커버력", "밀착력",
        "세정력", "톤업", "보습", "진정", "미백", "주름", "탄력", "향",
        "장점", "단점", "장단점", "주의점",
    ]
    for attr in attributes:
        if attr in query:
            return attr
    return None
