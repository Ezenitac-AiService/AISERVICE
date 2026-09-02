"""Document-Level Dynamic Top-P (Nucleus) Selection & Score Cliff Truncation (Spec 037 FR-004, FR-005).

Calculates cumulative relevance mass over BGE-Reranker scores and adaptively
selects optimal high-quality reviews while cutting off tail noise and score cliffs.
"""

import math
from typing import List, Dict, Any, Tuple, Optional
from ..models.citation_models import DocumentTopPConfig, ReviewCitation
from ..logger import get_logger

logger = get_logger("oliview.top_p.document")


class DocumentTopPCalculator:
    """리뷰 문서 동적 Top-P 선별 및 점수 절벽 컷오프 계산기."""

    def __init__(self, config: Optional[DocumentTopPConfig] = None):
        self.config = config or DocumentTopPConfig()

    def filter_documents(
        self,
        candidate_docs: List[Dict[str, Any]],
        target_name: str = "",
        short_target_name: str = "",
    ) -> List[ReviewCitation]:
        """BGE-Reranker 점수가 부여된 후보 문서들을 입력받아 문서 동적 Top-P를 적용합니다.

        Args:
            candidate_docs: List of dicts with keys: 'text', 'score', 'rating', 'option', 'review_id'
            target_name: 대상 상품명
            short_target_name: 짧은 식별명 (예: '컬러그램 꿀로스')

        Returns:
            List of ReviewCitation objects passing the Top-P and Cliff gates.
        """
        if not candidate_docs:
            return []

        # 1. 점수 내림차순 정렬 (score 또는 rerank_score 지원)
        sorted_docs = sorted(
            candidate_docs,
            key=lambda x: float(x.get("score", x.get("rerank_score", 0.0))),
            reverse=True,
        )

        # 2. 1차 절대 품질 게이트 (Hard Gate: s_i >= min_score_gate)
        gated_docs = [
            d for d in sorted_docs
            if float(d.get("score", d.get("rerank_score", 0.0))) >= self.config.min_score_gate
        ]

        if not gated_docs:
            logger.info(f"[{target_name}] All {len(sorted_docs)} docs fell below min_score_gate {self.config.min_score_gate}")
            return []

        scores = [float(d.get("score", d.get("rerank_score", 0.0))) for d in gated_docs]

        # 3. 점수 절벽 (Score Cliff) 검사: 인접 문서 점수차가 0.25 이상 급락 시 조기 컷오프
        cutoff_index = len(scores)
        for i in range(len(scores) - 1):
            delta = scores[i] - scores[i + 1]
            if delta > self.config.score_cliff_delta:
                logger.info(f"[{target_name}] Score cliff detected between rank {i+1} ({scores[i]:.3f}) and {i+2} ({scores[i+1]:.3f}), delta={delta:.3f}. Truncating early.")
                cutoff_index = i + 1
                break

        cliff_docs = gated_docs[:cutoff_index]
        cliff_scores = scores[:cutoff_index]

        # 4. 확률 질량 정규화 (Softmax with temperature scaling)
        tau = self.config.temperature_scaling
        exp_scores = [math.exp(s / tau) for s in cliff_scores]
        sum_exp = sum(exp_scores)
        probs = [e / sum_exp for e in exp_scores]

        # 5. 누적 관련도 질량 (Cumulative Probability Mass >= 0.85) 선별
        selected_docs: List[Dict[str, Any]] = []
        cumulative_prob = 0.0

        for idx, (doc, prob) in enumerate(zip(cliff_docs, probs)):
            selected_docs.append(doc)
            cumulative_prob += prob

            if len(selected_docs) >= self.config.max_selected_docs:
                break
            if cumulative_prob >= self.config.cumulative_mass_threshold and len(selected_docs) >= self.config.min_selected_docs:
                break

        logger.info(
            f"[{target_name}] Document Top-P: Selected {len(selected_docs)}/{len(candidate_docs)} reviews "
            f"(Cumulative mass: {cumulative_prob:.3f}, Score range: {cliff_scores[0]:.3f} ~ {cliff_scores[len(selected_docs)-1]:.3f})"
        )

        # 6. ReviewCitation 객체로 변환 및 인용 태그 부여
        citations: List[ReviewCitation] = []

        for rank_idx, doc in enumerate(selected_docs, start=1):
            doc_target = short_target_name or doc.get("clean_product_name")
            if doc_target and doc_target != "unknown":
                tag = f"[{doc_target} 리뷰 {rank_idx}]"
            else:
                tag = f"[리뷰 {rank_idx}]"

            citations.append(ReviewCitation(
                citation_tag=tag,
                target_product_name=doc_target or target_name,
                review_id=str(doc.get("review_id", f"rev_{rank_idx}")),
                rating=int(doc.get("rating", 5)),
                product_option=str(doc.get("option", doc.get("product_option", "기본"))),
                snippet=str(doc.get("text", doc.get("snippet", ""))),
                rerank_score=float(doc.get("score", doc.get("rerank_score", 0.0))),
            ))

        return citations
