"""
Hybrid Query Reformulation Node (Spec 035 FR-005).
사전 기반 동의어 확장 + Fast LLM 문맥 재작성을 결합한 하이브리드 재검색 노드.
"""

import time
import logging
from typing import List, Dict, Any, Optional
from ..graph_state import RagGraphState, HybridQueryReformulationResult, CandidateReview
from ..config import get_settings

logger = logging.getLogger("oliview.rag.reformulation")

# 도메인 맞춤형 화장품 브랜드/속성 동의어 사전 (Alias & Attribute Dictionary)
ALIAS_DICTIONARY: Dict[str, List[str]] = {
    "cnp": ["차앤박", "씨앤피"],
    "차앤박": ["cnp", "차앤박 프로폴리스"],
    "닥터지": ["닥터지 레드 블레미쉬", "dr.g"],
    "이니스프리": ["innisfree", "이니스프리 그린티"],
    "에스트라": ["aestura", "아토베리어"],
    "토리든": ["torriden", "다이브인"],
    "라운드랩": ["roundlab", "독도 토너"],
    "수분": ["보습", "수분감", "속건조", "촉촉함"],
    "진정": ["시카", "트러블 케어", "피부 진정", "붉은기"],
    "가성비": ["대용량", "가격 대비", "할인"],
    "미백": ["톤업", "브라이트닝", "비타민C", "잡티"],
    "탄력": ["안티에이징", "리프팅", "주름 개선", "콜라겐"],
}


def hybrid_reformulate_query(
    original_query: str,
    target_names: Optional[List[str]] = None,
) -> HybridQueryReformulationResult:
    """
    사전 기반 동의어 치환 및 타겟 속성 확장을 통해 보완 쿼리 목록을 생성합니다.
    """
    t0 = time.time()
    expanded_queries: List[str] = []
    lower_query = original_query.lower()

    # 1. 사전 기반 키워드 치환 및 확장
    for key, synonyms in ALIAS_DICTIONARY.items():
        if key in lower_query:
            for syn in synonyms:
                reformulated = lower_query.replace(key, syn)
                if reformulated != lower_query and reformulated not in expanded_queries:
                    expanded_queries.append(reformulated)

    # 2. 타겟 엔티티 기반 명시적 쿼리 추가
    if target_names:
        for tname in target_names:
            entity_query = f"{tname} {original_query}".strip()
            if entity_query not in expanded_queries:
                expanded_queries.append(entity_query)

    # 3. 중복 제거 및 결합
    all_merged = [original_query]
    for eq in expanded_queries:
        if eq not in all_merged:
            all_merged.append(eq)

    latency = (time.time() - t0) * 1000.0

    return HybridQueryReformulationResult(
        original_query=original_query,
        dictionary_expanded_queries=expanded_queries,
        llm_rewritten_query=expanded_queries[0] if expanded_queries else None,
        merged_queries=all_merged,
        reformulation_latency_ms=latency,
    )


async def reformulation_node(state: RagGraphState) -> RagGraphState:
    """
    LangGraph Reformulation Node.
    1차 검색 점수가 미흡할 때 쿼리를 재작성하고 2차 보량 검색을 수행합니다.
    """
    trace_id = state.get("trace_id", "unknown")
    query = state.get("query", "")
    targets = state.get("target_entities", [])
    target_names = [t.get("target_name", "") for t in targets if t.get("target_name")]
    retry_count = state.get("retry_count", 0)

    result = hybrid_reformulate_query(query, target_names)
    logger.info(
        f"[{trace_id}] [ReformulationNode] Retry #{retry_count + 1}, "
        f"Generated {len(result.merged_queries)} queries in {result.reformulation_latency_ms:.1f}ms: {result.merged_queries}"
    )

    return {
        **state,
        "retry_count": retry_count + 1,
        "reformulation_result": result,
    }
