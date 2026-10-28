"""Reranker Node with Document-Level Dynamic Top-P & Score Cliff Truncation (Spec 037 FR-004, FR-005).
수집된 후보군을 단일 통합 배치로 리랭킹하고, 타겟별 문서 Top-P (85% 질량) 및 점수 절벽 컷오프로 독립 선별.
"""

import math
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


def sigmoid(z: float) -> float:
    """Normalize raw Cross-Encoder logit to probability in [0, 1]."""
    if z >= 40.0:
        return 1.0
    if z <= -40.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def apply_3guardrail_score_cliff(
    candidates: List[Dict[str, Any]],
    min_score_gate: float = 0.35,
    min_k: int = 2,
    cliff_delta: float = 0.15,
    high_conf_threshold: float = 0.65,
    max_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    3-Guardrail Dynamic Score Cliff Truncation (T011, T014):
    1. Filter out candidate documents with score < min_score_gate (0.35).
    2. Guardrail 1: Minimum quota min_k (default 2) preserved (no cliff cutoff before rank 2).
    3. Guardrail 2: High-confidence preservation (s_{i+1} >= high_conf_threshold 0.65 exempted from cliff).
    4. Guardrail 3: Max document cap max_k (default 5).
    """
    if not candidates:
        return []

    sorted_candidates = sorted(
        candidates,
        key=lambda c: c.get("rerank_score", c.get("score", 0.0)),
        reverse=True,
    )

    valid = [
        c for c in sorted_candidates
        if c.get("rerank_score", c.get("score", 0.0)) >= min_score_gate
    ]
    if not valid:
        return []

    cutoff_idx = len(valid)
    for i in range(len(valid) - 1):
        s_curr = valid[i].get("rerank_score", valid[i].get("score", 0.0))
        s_next = valid[i + 1].get("rerank_score", valid[i + 1].get("score", 0.0))
        delta = s_curr - s_next
        if delta >= cliff_delta:
            # Guardrail 1: Preserve minimum quota min_k
            if (i + 1) < min_k:
                continue
            # Guardrail 2: Preserve high confidence candidate
            if s_next >= high_conf_threshold:
                continue
            cutoff_idx = i + 1
            break

    # Guardrail 3: Cap at max_k
    return valid[:cutoff_idx][:max_k]


def reranker_node(state: RagGraphState) -> Dict[str, Any]:
    """
    단일 통합 배치 리랭킹 및 3중 가드레일 점수 절벽 동적 선별 노드 (Spec 037, T014).
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

        # 2. 리랭킹 점수 계산 (AiGatewayClient 호출: 원시 로짓 획득)
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
            scores = [c.get("first_stage_score", 0.0) for c in all_candidates]

        # 점수 매핑: raw_score 보존 및 Sigmoid 정규화 적용 (T014)
        for c, s in zip(all_candidates, scores):
            raw_val = float(s)
            c["raw_score"] = raw_val
            c["rerank_score"] = sigmoid(raw_val)

        # 3. 타겟별 파티션 및 3중 가드레일 점수 절벽 동적 컷오프 적용 (T031-B)
        target_max_k = 12 if len(target_offsets) <= 1 else max(4, 16 // len(target_offsets))

        for target_id, (start, end) in target_offsets.items():
            subset = all_candidates[start:end]
            if not subset:
                reranked_contexts[target_id] = []
                continue

            entity = entity_map.get(target_id, {})
            target_name = entity.get("target_name", subset[0].get("target_name", ""))

            # 3-Guardrail Dynamic Score Cliff Truncation with Dynamic Target Partitioning
            selected_candidates = apply_3guardrail_score_cliff(
                subset,
                min_score_gate=0.35,
                min_k=2,
                cliff_delta=0.15,
                high_conf_threshold=0.65,
                max_k=target_max_k,
            )

            # RerankedReview 변환
            selected_reviews: List[RerankedReview] = []
            for rank_idx, orig in enumerate(selected_candidates, start=1):
                selected_reviews.append(RerankedReview(
                    doc_id=orig.get("doc_id", ""),
                    review_id=orig.get("review_id"),
                    review_text=orig["review_text"],
                    target_id=target_id,
                    target_name=orig.get("target_name", target_name),
                    product_name=orig.get("product_name"),
                    clean_product_name=orig.get("clean_product_name"),
                    brand_name=orig.get("brand_name"),
                    category=orig.get("category"),
                    attribute_name=orig.get("attribute_name"),
                    product_url=orig.get("product_url"),
                    rerank_score=orig.get("rerank_score", 0.0),
                    raw_score=orig.get("raw_score", 0.0),
                    rank=rank_idx,
                    rating=orig.get("rating", 5.0),
                ))

            reranked_contexts[target_id] = selected_reviews
            logger.info(
                f"[{target_id}] 3중 가드레일 리랭킹 선별 완료: {len(selected_reviews)}건 (후보 {len(subset)}건 중)",
                extra={
                    "trace_id": trace_id,
                    "doc_count": len(selected_reviews),
                    "target_id": target_id,
                },
            )

    return {
        "reranked_contexts": reranked_contexts,
        "is_fallback": is_fallback,
        "fallback_reason": fallback_reason,
    }
