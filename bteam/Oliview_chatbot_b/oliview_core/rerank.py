"""
BGE Cross-Encoder Reranker Module with GPU remote offload and 0ms primary similarity fallback.
Spec 030 & Feature 045: CPU local CrossEncoder fallback completely removed (FR-007).
"""

from typing import List, Tuple, Optional
from .client import AiGatewayClient
from .config import get_settings
from .logger import get_logger

logger = get_logger("oliview.rerank")


class BGEReranker:
    """High-speed GPU Reranker with 0ms primary similarity safe fallback."""

    def __init__(self, client: Optional[AiGatewayClient] = None):
        self.client = client or AiGatewayClient()
        self.settings = get_settings()

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5,
    ) -> Tuple[List[int], List[float], bool]:
        """
        Reranks candidate documents against query.
        Returns:
          - ranked_indices: List[int] indices in descending score order
          - sorted_scores: List[float] corresponding scores
          - fallback_used: bool whether safe 1st-stage similarity fallback was used
        """
        if not documents:
            return [], [], False

        fallback_used = False
        try:
            # 1. High-speed GPU remote reranking (approx 0.03s ~ 0.05s)
            scores = self.client.rerank(query, documents)
            if scores is None or len(scores) < len(documents):
                raise ValueError("Remote GPU reranker returned None or incomplete score list")
        except Exception as e:
            # 2. Spec 030 / Feature 045: 0ms Safe Fallback using initial candidate similarity order
            logger.warning(f"GPU 리랭커 실패 -> 1차 유사도 안전 폴백 가동: {e}")
            fallback_used = True
            scores = [max(0.0, 0.85 - (i * 0.05)) for i in range(len(documents))]

        if scores is None or not scores:
            scores = [max(0.0, 0.85 - (i * 0.05)) for i in range(len(documents))]

        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_indexed = indexed_scores[:top_k]

        ranked_indices = [idx for idx, _ in top_indexed]
        sorted_scores = [score for _, score in top_indexed]

        return ranked_indices, sorted_scores, fallback_used
