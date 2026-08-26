"""
Self-RAG Quality Grade Node (Spec 035 FR-005).
1차 검색 및 리랭킹 결과의 관련성 점수와 타겟별 충분성을 평가하여 재검색 필요 여부를 판정합니다.
"""

import logging
from typing import Dict, List, Any, Optional
from ..graph_state import QualityGradeVerdict, RerankedReview, RagGraphState

logger = logging.getLogger("oliview.rag.quality_grade")


def evaluate_search_quality(
    reranked_contexts: Dict[str, List[Dict[str, Any]]],
    min_threshold: float = 0.35,
    min_reviews_per_target: int = 1,
) -> QualityGradeVerdict:
    if not reranked_contexts:
        return QualityGradeVerdict(
            status="RETRY_SEARCH",
            average_score=0.0,
            min_score=0.0,
            total_candidates_found=0,
            missing_targets=[],
            reason="검색 결과 컨텍스트가 비어 있음",
        )

    all_scores: List[float] = []
    missing_targets: List[str] = []
    total_docs = 0

    for target_id, reviews in reranked_contexts.items():
        if not reviews or len(reviews) < min_reviews_per_target:
            missing_targets.append(target_id)
            continue
        for r in reviews:
            score = float(r.get("rerank_score", 0.0))
            all_scores.append(score)
            total_docs += 1

    if missing_targets:
        return QualityGradeVerdict(
            status="RETRY_SEARCH",
            average_score=sum(all_scores) / len(all_scores) if all_scores else 0.0,
            min_score=min(all_scores) if all_scores else 0.0,
            total_candidates_found=total_docs,
            missing_targets=missing_targets,
            reason=f"일부 타겟 검색 결과 부족: {missing_targets}",
        )

    if not all_scores:
        return QualityGradeVerdict(
            status="RETRY_SEARCH",
            average_score=0.0,
            min_score=0.0,
            total_candidates_found=0,
            missing_targets=list(reranked_contexts.keys()),
            reason="유효한 리랭킹 점수가 없음",
        )

    avg_score = sum(all_scores) / len(all_scores)
    min_score = min(all_scores)

    if avg_score < min_threshold:
        return QualityGradeVerdict(
            status="RETRY_SEARCH",
            average_score=avg_score,
            min_score=min_score,
            total_candidates_found=total_docs,
            missing_targets=[],
            reason=f"평균 리랭킹 점수 미달 ({avg_score:.3f} < {min_threshold})",
        )

    return QualityGradeVerdict(
        status="PASSED",
        average_score=avg_score,
        min_score=min_score,
        total_candidates_found=total_docs,
        missing_targets=[],
        reason="검색 품질 기준 충족",
    )


async def quality_grade_node(state: RagGraphState) -> RagGraphState:
    reranked = state.get("reranked_contexts", {})
    verdict = evaluate_search_quality(reranked, min_threshold=0.35)
    
    logger.info(
        f"[{state.get('trace_id', 'unknown')}] [QualityGradeNode] "
        f"Status: {verdict.status}, Avg Score: {verdict.average_score:.3f}, Docs: {verdict.total_candidates_found}"
    )
    
    return {
        **state,
        "quality_verdict": verdict,
    }
