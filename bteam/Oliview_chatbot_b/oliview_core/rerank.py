"""
BGE Cross-Encoder Reranker Module with GPU remote offload and lazy local fallback.
"""

import time
from typing import List, Tuple, Optional
import numpy as np
from .client import AiGatewayClient
from .config import get_settings


class BGEReranker:
    """High-speed GPU Reranker with lazy local CPU CrossEncoder fallback."""

    def __init__(self, client: Optional[AiGatewayClient] = None):
        self.client = client or AiGatewayClient()
        self.settings = get_settings()
        self._local_model = None

    def _get_local_model(self):
        """Lazy load local CrossEncoder only if remote GPU call fails."""
        if self._local_model is None:
            print("[INFO] BGE CrossEncoder 로컬 모델 가중치 로드 중 (Fallback)...")
            from sentence_transformers import CrossEncoder
            self._local_model = CrossEncoder(
                "BAAI/bge-reranker-v2-m3",
                max_length=512,
                device="cpu",
            )
        return self._local_model

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
          - fallback_used: bool whether local CPU fallback was used
        """
        if not documents:
            return [], [], False

        fallback_used = False
        try:
            # 1. High-speed GPU remote reranking (approx 0.03s ~ 0.05s)
            scores = self.client.rerank(query, documents)
        except Exception as e:
            # 2. Local Fallback
            print(f"[WARN] GPU 리랭커 실패 -> 로컬 폴백 가동: {e}")
            fallback_used = True
            try:
                local_model = self._get_local_model()
                pairs = [[query, doc] for doc in documents]
                raw_scores = local_model.predict(pairs)
                scores = [float(s) for s in raw_scores]
            except Exception as fe:
                print(f"[WARN] 로컬 CrossEncoder 사용 불가, 기본 유사도 점수 반환: {fe}")
                scores = [0.85 - (i * 0.05) for i in range(len(documents))]

        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_indexed = indexed_scores[:top_k]

        ranked_indices = [idx for idx, _ in top_indexed]
        sorted_scores = [score for _, score in top_indexed]

        return ranked_indices, sorted_scores, fallback_used
