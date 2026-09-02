"""
Search Subgraph Node (Spec 030 FR-003 / FR-018).
LangGraph `Send` API 기반 타겟별 병렬 하이브리드 검색 노드.
타겟별 독립 검색 및 부분 장애 격리(Fault-Isolation) 지원.
"""

import time
from typing import Dict, Any, List, Optional

from ..config import get_settings
from ..graph_state import (
    RagGraphState, TargetEntity, CandidateReview,
    SubStepEvent, SubStepAction, StepStatus,
)
from ..retrieval import HybridRetriever
from ..redis_pool import cache_get, cache_set, build_l1_key, SingleFlightLock
from ..logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.node.search")

# 공유 Retriever 인스턴스 (Lazy init)
_retriever: Optional[HybridRetriever] = None


def _get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever


def search_single_target(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    단일 타겟에 대한 하이브리드 검색을 수행하는 LangGraph 노드.
    `Send` API를 통해 각 타겟별로 독립 호출됩니다.

    부분 장애 격리 (FR-018):
      - 1개 타겟의 DB/검색 실패 시 해당 타겟만 빈 결과로 설정
      - 나머지 정상 타겟은 영향 없이 진행
    """
    trace_id = state.get("trace_id", get_trace_id())
    query = state.get("normalized_query", state.get("query", ""))
    target: TargetEntity = state.get("current_target", {})
    target_id = target.get("target_id", "unknown")
    target_name = target.get("target_name", "unknown")
    brand_name = target.get("brand_name")
    attribute_query = target.get("attribute_query")
    settings = get_settings()

    candidates: List[CandidateReview] = []
    error_msg: Optional[str] = None

    with StepTimer("SEARCH", trace_id=trace_id, target_id=target_id):
        try:
            # 1. L1 캐시 조회
            l1_key = build_l1_key(
                _normalize_slug(target_name),
                _normalize_slug(attribute_query or "default"),
            )
            cached_pool = cache_get(l1_key)
            if cached_pool is not None:
                logger.info(
                    f"[{target_id}] L1 캐시 히트 ({len(cached_pool)}건)",
                    extra={"trace_id": trace_id, "cache_hit": True, "target_id": target_id},
                )
                candidates = cached_pool[:settings.candidates_per_target]
            else:
                # 2. Single-flight 락 획득 (캐시 스탬피드 방어)
                slug = _normalize_slug(target_name)
                lock_acquired = SingleFlightLock.acquire(slug)

                try:
                    # 3. 하이브리드 검색 실행
                    retriever = _get_retriever()

                    # 속성 키워드가 있으면 쿼리에 추가
                    search_query = query
                    if attribute_query and attribute_query not in query:
                        search_query = f"{query} {attribute_query}"

                    raw_results = retriever.search(
                        query=search_query,
                        top_k=settings.candidates_per_target,
                        brand_filter=brand_name,
                        auto_detect_filter=True,
                    )

                    from oliview_core.sanitizer import clean_product_name_for_search, build_oliveyoung_url

                    # 4. CandidateReview 구조로 변환 (제품명 컨텍스트 포함)
                    for idx, r in enumerate(raw_results):
                        raw_p_name = r.get("product_name") or ""
                        p_name = raw_p_name if raw_p_name and raw_p_name != "unknown" else target_name
                        b_name = r.get("brand") or r.get("brand_name") or brand_name or ""
                        c_name = r.get("category") or "화장품"
                        attr_name = r.get("attribute_name") or ""
                        r_text = r.get("review_text", r.get("clean_text", "")).strip()

                        clean_p_name = clean_product_name_for_search(p_name, b_name)

                        # 제품명 프리픽스 추가 (열린 질의/추천 시 제품 식별력 보장)
                        if p_name and p_name != "unknown" and not r_text.startswith(f"[{p_name}]"):
                            full_review_text = f"[{p_name}] {r_text}"
                        else:
                            full_review_text = r_text

                        p_url = build_oliveyoung_url(clean_p_name, b_name)

                        candidates.append(CandidateReview(
                            doc_id=str(r.get("review_id", idx)),
                            review_text=full_review_text,
                            target_id=target_id,
                            target_name=p_name if p_name != "unknown" else target_name,
                            product_name=p_name,
                            clean_product_name=clean_p_name,
                            brand_name=b_name,
                            category=c_name,
                            attribute_name=attr_name,
                            product_url=p_url,
                            first_stage_score=float(r.get("dense_score", 0.5)),
                            rating=r.get("rating", 5.0),
                            skin_type=r.get("skin_type"),
                        ))

                    # 5. L1 캐시 저장 (TTL 12h)
                    if candidates and lock_acquired:
                        cache_set(l1_key, candidates, settings.redis_ttl_search_pool)

                finally:
                    if lock_acquired:
                        SingleFlightLock.release(slug)

            logger.info(
                f"[{target_id}] {target_name} 검색 완료: {len(candidates)}건",
                extra={
                    "trace_id": trace_id,
                    "target_id": target_id,
                    "doc_count": len(candidates),
                },
            )

        except Exception as e:
            # 부분 장애 격리: 개별 타겟 실패 시 빈 결과로 진행
            error_msg = f"{target_name} 검색 실패: {e}"
            logger.warning(
                error_msg,
                extra={
                    "trace_id": trace_id,
                    "target_id": target_id,
                    "error_type": type(e).__name__,
                    "fallback": True,
                },
            )

    # 상태 업데이트 (부분 병합)
    update: Dict[str, Any] = {
        "search_pools": {target_id: candidates},
    }
    if error_msg:
        update["target_errors"] = {target_id: error_msg}
        update["error_log"] = [error_msg]

    return update


def _normalize_slug(text: str) -> str:
    """캐시 키용 슬러그 정규화."""
    if not text:
        return "default"
    import re
    slug = re.sub(r"[^a-zA-Z0-9가-힣]", "_", text.strip().lower())
    return slug[:50]
