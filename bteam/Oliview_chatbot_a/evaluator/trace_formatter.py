"""
Result Console Formatter for Trainee Traceability & Debugging Display
"""

from typing import List, Optional
from evaluator.models import HybridSearchResult

class ResultConsoleFormatter:
    """
    훈련생 학습용 검색 출처 박스 및 60자 프리뷰 트렁킹 포맷터
    """

    @staticmethod
    def truncate_preview(text: str, max_len: int = 60) -> str:
        """텍스트 본문을 max_len 길이 내외로 자르고 '...' 부착"""
        if not text:
            return ""
        clean_text = text.strip().replace("\n", " ")
        if len(clean_text) <= max_len:
            return clean_text
        return clean_text[:max_len] + "..."

    @classmethod
    def format_results(
        cls,
        results: List[HybridSearchResult],
        alpha: float = 0.5,
        max_preview_len: int = 60,
    ) -> str:
        """
        검색 결과 리스트를 콘솔 포맷팅 박스 형태의 텍스트 문자열로 변환합니다.
        """
        lines = []
        lines.append("=" * 80)
        lines.append(f"[하이브리드 검색 결과 (Total: {len(results)}, Alpha: {alpha:.2f})]")
        lines.append("=" * 80)

        if not results:
            lines.append("  (일치하는 검색 결과가 없습니다)")
            lines.append("=" * 80)
            return "\n".join(lines)

        for rank, res in enumerate(results, 1):
            lines.append(f"[Rank {rank}] Source: {res.source_file} | Chunk ID: {res.chunk_id}")
            lines.append(f"- Matched Keywords: {res.matched_keywords}")
            lines.append(
                f"- Scores: Hybrid={res.hybrid_score:.4f} "
                f"(Vector={res.vector_score:.4f}, Keyword={res.keyword_score:.4f})"
            )
            preview = cls.truncate_preview(res.raw_chunk_text or res.text_preview, max_len=max_preview_len)
            lines.append(f'- Preview: "{preview}"')
            if rank < len(results):
                lines.append("-" * 80)

        lines.append("=" * 80)
        return "\n".join(lines)

    @classmethod
    def print_results(
        cls,
        results: List[HybridSearchResult],
        alpha: float = 0.5,
        max_preview_len: int = 60,
    ) -> None:
        """
        검색 결과를 콘솔에 직접 출력합니다.
        """
        output = cls.format_results(results, alpha=alpha, max_preview_len=max_preview_len)
        print(output)
