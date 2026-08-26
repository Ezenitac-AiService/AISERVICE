"""
Reranker Node with Per-Target Quota Partitioning (Spec 030 FR-006 / FR-007 / FR-011).
수집된 후보군을 단일 통합 배치로 리랭킹하고, 타겟별 쿼터로 독립 선별.
5.0s 타임아웃 초과 시 0ms 1차 유사도 순위 유지 안전 폴백.
"""

import time
from typing import Dict, Any, List

from ..config import get_settings
from ..graph_state import (
    RagGraphState, CandidateReview, RerankedReview,
    FALLBACK_LABEL,
)
from ..client import AiGatewayClient
from ..logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.node.rerank")


def reranker_node(state: RagGraphState) -> Dict[str, Any]:
    """
    단일 통합 배치 리랭킹 및 타겟별 쿼터 파티셔닝 노드.

    동작 흐름:
    1. 모든 타겟의 후보 문서를 단일 리스트로 병합
    2. 3건 이하 단축 경로 (FR-011): 리랭킹 스킵
    3. 단일 통합 배치로 8091 GPU 리랭킹 (5.0s 타임아웃)
    4. 타임아웃 시 0ms 즉각 1차 유사도 순위 유지 (안전 폴백)
    5. 타겟별 쿼터 파티셔닝: 각 타겟에서 상위 2~3건 독립 선별
    """
    trace_id = state.get("trace_id", get_trace_id())
    query = state.get("normalized_query", state.get("query", ""))
    search_pools = state.get("search_pools", {})
    settings = get_settings()

    reranked_contexts: Dict[str, List[RerankedReview]] = {}
    is_fallback = False
    fallback_reason = None
    metrics_update: Dict[str, Any] = {}

    with StepTimer("RERANK", trace_id=trace_id) as timer:
        # 1. 모든 후보를 단일 리스트로 병합
        all_candidates: List[CandidateReview] = []
        target_offsets: Dict[str, tuple] = {}  # {target_id: (start_idx, end_idx)}

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

        # 2. 단축 경로 (FR-011): 3건 이하면 리랭킹 스킵
        if len(all_candidates) <= 3:
            logger.info(
                f"후보 {len(all_candidates)}건 — 단축 경로 (리랭킹 스킵)",
                extra={"trace_id": trace_id, "doc_count": len(all_candidates)},
            )
            for target_id, (start, end) in target_offsets.items():
                subset = all_candidates[start:end]
                reranked_contexts[target_id] = [
                    RerankedReview(
                        doc_id=c["doc_id"],
                        review_text=c["review_text"],
                        target_id=c["target_id"],
                        target_name=c["target_name"],
                        rerank_score=c["first_stage_score"],
                        rank=idx + 1,
                    )
                    for idx, c in enumerate(subset[:settings.reranked_per_target])
                ]
            return {
                "reranked_contexts": reranked_contexts,
                "is_fallback": False,
            }

        # 3. 단일 통합 배치 리랭킹 (5.0s 타임아웃)
        all_texts = [c["review_text"] for c in all_candidates]
        client = AiGatewayClient()

        scores = client.rerank(query, all_texts, trace_id=trace_id)

        if scores is None:
            # 4. 타임아웃/장애 — 0ms 즉각 1차 유사도 순위 유지 폴백
            is_fallback = True
            fallback_reason = "리랭커 5.0s 타임아웃 또는 GPU 장애"
            logger.warning(
                f"리랭커 폴백 발동: {fallback_reason}",
                extra={"trace_id": trace_id, "fallback": True},
            )
            # 1차 유사도 점수(first_stage_score)로 대체
            scores = [c["first_stage_score"] for c in all_candidates]

        # 5. 타겟별 쿼터 파티셔닝 (FR-006: 특정 제품 쏠림 0% 보장)
        for target_id, (start, end) in target_offsets.items():
            target_candidates = all_candidates[start:end]
            target_scores = scores[start:end]

            # 점수 기준 내림차순 정렬
            indexed = list(enumerate(zip(target_candidates, target_scores)))
            indexed.sort(key=lambda x: x[1][1], reverse=True)

            # 타겟별 쿼터 선별 (16K: 5~8건, 32K: 10~15건 동적 확장)
            harness = state.get("context_harness") or settings.get_context_harness()
            quota = harness.reranked_per_target
            selected = indexed[:quota]

            reranked_contexts[target_id] = [
                RerankedReview(
                    doc_id=cand.get("doc_id", str(rank_idx)),
                    review_text=cand.get("review_text", ""),
                    target_id=cand.get("target_id", target_id),
                    target_name=cand.get("target_name", target_id),
                    product_name=cand.get("product_name") or cand.get("target_name"),
                    brand_name=cand.get("brand_name", ""),
                    category=cand.get("category", "화장품"),
                    attribute_name=cand.get("attribute_name", ""),
                    product_url=cand.get("product_url", "#"),
                    rerank_score=float(score),
                    rank=rank_idx + 1,
                    rating=cand.get("rating", 5.0),
                )
                for rank_idx, (_, (cand, score)) in enumerate(selected)
            ]

        total_selected = sum(len(v) for v in reranked_contexts.values())
        logger.info(
            f"리랭킹 완료: 후보 {len(all_candidates)}건 → 선별 {total_selected}건 "
            f"(타겟 {len(reranked_contexts)}개, 폴백={'Y' if is_fallback else 'N'})",
            extra={
                "trace_id": trace_id,
                "step_id": "RERANK",
                "doc_count": total_selected,
                "fallback": is_fallback,
            },
        )

    metrics_update["rerank_latency_ms"] = timer.elapsed_ms

    result: Dict[str, Any] = {
        "reranked_contexts": reranked_contexts,
        "is_fallback": is_fallback,
    }
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    if metrics_update:
        result["metrics"] = metrics_update

    return result
