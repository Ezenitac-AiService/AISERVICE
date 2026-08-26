"""Reranker Node with Document-Level Dynamic Top-P & Score Cliff Truncation (Spec 037 FR-004, FR-005).
수집된 후보군을 단일 통합 배치로 리랭킹하고, 타겟별 문서 Top-P (85% 질량) 및 점수 절벽 컷오프로 독립 선별.
"""

import time
from typing import Dict, Any, List

from ..config import get_settings
from ..graph_state import (
    RagGraphState, CandidateReview, RerankedReview,
    FALLBACK_LABEL,
)
from ..client import AiGatewayClient
from ..utils.document_top_p import DocumentTopPCalculator
from ..logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.node.rerank")
_top_p_calc = DocumentTopPCalculator()


def reranker_node(state: RagGraphState) -> Dict[str, Any]:
    """
    단일 통합 배치 리랭킹 및 문서 동적 Top-P 선별 노드 (Spec 037).
    """
    trace_id = state.get("trace_id", get_trace_id())
    query = state.get("normalized_query", state.get("query", ""))
    search_pools = state.get("search_pools", {})
    target_entities = state.get("target_entities", [])
    settings = get_settings()

    entity_map = {e["target_id"]: e for e in target_entities}
    reranked_contexts: Dict[str, List[RerankedReview]] = {}
    is_fallback = False
    fallback_reason = None

    with StepTimer("RERANK", trace_id=trace_id):
        # 1. 모든 후보를 단일 리스트로 병합
        all_candidates: List[CandidateReview] = []
        target_offsets: Dict[str, tuple] = {}

        for target_id, candidates in search_pools.items():
            start = len(all_candidates)
            all_candidates.extend(candidates)
            end = len(all_candidates)
            target_offsets[target_id] = (start, end)

        if not all_candidates:
            return {
                "reranked_contexts": {},
                "is_fallback": True,
                "fallback_reason": "검색 결과 0건",
            }

        # 2. 리랭킹 점수 계산 (AiGatewayClient 호출)
        all_texts = [c["review_text"] for c in all_candidates]
        client = AiGatewayClient()

        timeout_sec = settings.timeout_rerank_sec
        scores = client.rerank(query, all_texts, timeout=timeout_sec, trace_id=trace_id)

        if scores is None:
            is_fallback = True
            fallback_reason = f"리랭커 {timeout_sec:.1f}s 타임아웃 또는 GPU 장애"
            logger.warning(
                f"리랭커 폴백 발동: {fallback_reason}",
                extra={"trace_id": trace_id, "fallback": True},
            )
            scores = [c["first_stage_score"] for c in all_candidates]

        # 점수 매핑
        for c, s in zip(all_candidates, scores):
            c["rerank_score"] = float(s)

        # 3. 타겟별 파티션 및 문서 동적 Top-P (85% 누적 질량 + Cliff 0.25 컷오프) 적용
        for target_id, (start, end) in target_offsets.items():
            subset = all_candidates[start:end]
            if not subset:
                reranked_contexts[target_id] = []
                continue

            entity = entity_map.get(target_id, {})
            target_name = entity.get("target_name", subset[0]["target_name"])

            candidate_dicts = [
                {
                    "score": c.get("rerank_score", 0.0),
                    "text": c["review_text"],
                    "review_id": c.get("doc_id", ""),
                    "rating": c.get("rating", 5),
                    "option": c.get("option", "기본"),
                }
                for c in subset
            ]

            # Document Top-P 적용
            citations = _top_p_calc.filter_documents(
                candidate_dicts,
                target_name=target_name,
            )

            # RerankedReview 변환
            selected_reviews: List[RerankedReview] = []
            for rank_idx, cit in enumerate(citations, start=1):
                selected_reviews.append(RerankedReview(
                    doc_id=cit.review_id,
                    review_text=cit.snippet,
                    target_id=target_id,
                    target_name=target_name,
                    rerank_score=cit.rerank_score,
                    rank=rank_idx,
                ))

            # 최소 1건 보장: 만약 Top-P에서 0건으로 모두 탈락했으나 원본 후보가 있었다면 최고점 1건 보존
            if not selected_reviews and subset:
                best = max(subset, key=lambda x: x.get("rerank_score", 0.0))
                selected_reviews.append(RerankedReview(
                    doc_id=best["doc_id"],
                    review_text=best["review_text"],
                    target_id=target_id,
                    target_name=target_name,
                    rerank_score=best.get("rerank_score", 0.0),
                    rank=1,
                ))

            reranked_contexts[target_id] = selected_reviews
            logger.info(
                f"[{target_id}] Document Top-P 선별 완료: {len(selected_reviews)}건 선별",
                extra={"trace_id": trace_id, "doc_count": len(selected_reviews)},
            )

    return {
        "reranked_contexts": reranked_contexts,
        "is_fallback": is_fallback,
        "fallback_reason": fallback_reason,
    }
