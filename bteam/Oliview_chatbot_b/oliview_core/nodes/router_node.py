"""Intent Router Node (Spec 030 / Spec 037 - Hybrid Cascaded Entity Normalization & Discovery).
사용자 질의의 의도를 분류하고 분석 대상 엔티티를 정규화/발굴하는 LangGraph 노드.
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
from ..utils.entity_normalizer import HybridEntityNormalizer
from ..tools.search_tools import tool_search_catalog
from ..logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.node.router")

_normalizer = HybridEntityNormalizer()


def intent_router_node(state: RagGraphState) -> Dict[str, Any]:
    """
    LangGraph 의도 분류 및 엔티티 추출 노드 (Spec 037 하이브리드 캐스케이디드 파서 탑재).
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

        # 1. 하이브리드 캐스케이디드 엔티티 정규화 (Spec 037 FR-001)
        norm_result = _normalizer.normalize(query)
        normalized_query, detected_brands = normalize_query_brands(query)

        # 2. 패턴 분류
        if norm_result.is_discovery:
            pattern_type = PatternType.FEATURE_DISCOVERY
        elif norm_result.intent.value == "COMPARISON" or len(detected_brands) >= 2:
            pattern_type = PatternType.EXPLICIT_COMPARE
        elif norm_result.extracted_aspects:
            pattern_type = PatternType.ASPECT_PROS_CONS
        else:
            pattern_type = PatternType.SINGLE_TARGET

        # 3. 타겟 엔티티 추출 및 Discovery 자동 발굴 (Spec 037 FR-002)
        target_entities: List[TargetEntity] = []

        if pattern_type == PatternType.FEATURE_DISCOVERY:
            # 카테고리/속성 기반 올리브영 DB 실존 인기 상품 3~5개 자동 발굴
            search_cat = norm_result.extracted_category or query
            candidates = tool_search_catalog(query=search_cat, category=norm_result.extracted_category, limit=settings.max_targets)

            if candidates:
                for idx, c in enumerate(candidates):
                    target_entities.append(TargetEntity(
                        target_id=f"target_{idx + 1}",
                        target_name=c["product_name"],
                        brand_name=c.get("brand_name"),
                        product_name=c["product_name"],
                        target_type=TargetType.PRODUCT,
                        attribute_query=" ".join(norm_result.extracted_aspects) or None,
                        spec_header=None,
                    ))
            else:
                # DB 매칭 후보가 없는 경우 단일 검색 풀로 폴백
                target_entities.append(TargetEntity(
                    target_id="discovery_pool",
                    target_name=query[:50],
                    brand_name=None,
                    product_name=None,
                    target_type=TargetType.ATTRIBUTE,
                    attribute_query=" ".join(norm_result.extracted_aspects) or None,
                    spec_header=None,
                ))

        elif pattern_type == PatternType.EXPLICIT_COMPARE:
            for idx, brand in enumerate(detected_brands[:settings.max_targets]):
                target_entities.append(TargetEntity(
                    target_id=f"target_{idx + 1}",
                    target_name=brand,
                    brand_name=brand,
                    product_name=None,
                    target_type=TargetType.PRODUCT,
                    attribute_query=" ".join(norm_result.extracted_aspects) or None,
                    spec_header=None,
                ))

        else:  # SINGLE_TARGET / ASPECT_PROS_CONS
            resolved_target = norm_result.extracted_product or (detected_brands[0] if detected_brands else None) or query[:40]
            target_entities.append(TargetEntity(
                target_id="target_1",
                target_name=resolved_target,
                brand_name=norm_result.extracted_brand or (detected_brands[0] if detected_brands else None),
                product_name=norm_result.extracted_product,
                target_type=TargetType.PRODUCT,
                attribute_query=" ".join(norm_result.extracted_aspects) or None,
                spec_header=None,
            ))

        logger.info(
            f"의도 분류 완료: {pattern_type.value}, 타겟 {len(target_entities)}건 ({[t['target_name'] for t in target_entities]})",
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
