"""LangGraph Typed Spec Lookup Tool for Olive Young Products (Spec 037 FR-002)."""
from typing import Dict, Any, Optional
from ..logger import get_logger

logger = get_logger("oliview.tools.spec")


def tool_get_specs(product_name: str) -> Optional[Dict[str, Any]]:
    """상품 등록 기본 스펙 정보(브랜드, 가격, 용량, 주요 특징, 성분 등)를 조회합니다.

    Args:
        product_name: 조회 대상 상품명

    Returns:
        Dict with product specification header, or None if not found.
    """
    try:
        from ..retrieval import resolve_chroma_dir
        # ChromaDB 메타데이터에서 첫 번째 매칭 아이템의 스펙 정보 확인
        from .search_tools import get_retriever
        retriever = get_retriever()

        for doc, meta in zip(retriever.all_documents, retriever.all_metadatas):
            p_name = meta.get("product_name") or meta.get("name")
            if p_name and (product_name.lower() in p_name.lower() or p_name.lower() in product_name.lower()):
                return {
                    "product_name": p_name,
                    "brand_name": meta.get("brand_name", ""),
                    "category": meta.get("category", "화장품"),
                    "price": meta.get("price", "올리브영 공식 매장가 참조"),
                    "volume": meta.get("volume", "기본 규격"),
                    "skin_type": meta.get("skin_type", "모든 피부용"),
                    "features": meta.get("features", "올리브영 베스트셀러"),
                }

        return None
    except Exception as e:
        logger.warning(f"tool_get_specs failed: {e}")
        return None
