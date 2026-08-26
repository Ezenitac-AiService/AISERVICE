"""LangGraph Typed Search Tools for Olive Young Catalog & Reviews (Spec 037 FR-002)."""
from typing import List, Dict, Any, Optional
from ..retrieval import HybridRetriever
from ..client import AiGatewayClient
from ..logger import get_logger

logger = get_logger("oliview.tools.search")

_global_retriever: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    global _global_retriever
    if _global_retriever is None:
        _global_retriever = HybridRetriever()
    return _global_retriever


def tool_search_catalog(query: str, category: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """올리브영 상품 카탈로그에서 질의 및 카테고리에 부합하는 상위 실존 상품 목록을 검색합니다.

    Args:
        query: 검색어 (브랜드명 또는 카테고리/속성 키워드)
        category: 카테고리 필터 (선택)
        limit: 최대 반환 상품 수 (기본: 5)

    Returns:
        List of candidate product dictionaries with metadata.
    """
    retriever = get_retriever()
    try:
        # ChromaDB 메타데이터 및 BM25 코퍼스에서 고유 상품명 인출
        matching_products: Dict[str, Dict[str, Any]] = {}
        for doc, meta in zip(retriever.all_documents, retriever.all_metadatas):
            p_name = meta.get("product_name") or meta.get("name")
            if not p_name:
                continue

            # 카테고리 필터 검사
            p_cat = meta.get("category", "")
            if category and category not in p_cat and category not in p_name:
                continue

            # 검색어 매칭
            if query.lower() in p_name.lower() or any(term in p_name for term in query.split()):
                if p_name not in matching_products:
                    matching_products[p_name] = {
                        "product_id": meta.get("product_id", str(hash(p_name))),
                        "product_name": p_name,
                        "brand_name": meta.get("brand_name", ""),
                        "category_name": p_cat,
                        "avg_rating": float(meta.get("rating", 4.5)),
                        "review_sample_count": 1,
                    }
                else:
                    matching_products[p_name]["review_sample_count"] += 1

            if len(matching_products) >= limit * 3:
                break

        sorted_products = sorted(
            matching_products.values(),
            key=lambda x: (x["review_sample_count"], x["avg_rating"]),
            reverse=True,
        )
        return sorted_products[:limit]

    except Exception as e:
        logger.warning(f"tool_search_catalog failed: {e}")
        return []


def tool_search_series_candidates(
    series_keyword: str,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """시리즈/라인명(예: '센슈얼', '프로폴리스') 및 브랜드명을 기반으로 카탈로그에서 하위 실존 상품 후보 2~3종을 자동 발굴합니다.

    Args:
        series_keyword: 시리즈/라인명 핵심 키워드 (예: '센슈얼', '쥬시', '프로폴리스')
        brand: 브랜드명 필터 (예: '헤라', '차앤박', '롬앤')
        category: 카테고리 필터 (선택)
        limit: 최대 반환 후보 상품 수 (기본: 3)

    Returns:
        List of candidate product dictionaries with metadata.
    """
    retriever = get_retriever()
    try:
        matching_products: Dict[str, Dict[str, Any]] = {}
        clean_keyword = series_keyword.strip().lower()
        clean_brand = (brand or "").strip().lower()

        for doc, meta in zip(retriever.all_documents, retriever.all_metadatas):
            p_name = meta.get("product_name") or meta.get("name")
            if not p_name:
                continue

            p_name_lower = p_name.lower()
            p_brand_lower = (meta.get("brand_name") or "").lower()
            p_cat = meta.get("category", "")

            # 1) 브랜드 조건 검사
            if clean_brand and (clean_brand not in p_brand_lower and clean_brand not in p_name_lower):
                continue

            # 2) 카테고리 필터 검사
            if category and category not in p_cat and category not in p_name:
                continue

            # 3) 시리즈 키워드 서브스트링 매칭
            keyword_tokens = clean_keyword.split()
            matches_series = any(token in p_name_lower for token in keyword_tokens if len(token) >= 2)

            if matches_series:
                if p_name not in matching_products:
                    matching_products[p_name] = {
                        "product_id": meta.get("product_id", str(hash(p_name))),
                        "product_name": p_name,
                        "brand_name": meta.get("brand_name") or brand or "",
                        "category_name": p_cat,
                        "avg_rating": float(meta.get("rating", 4.5)),
                        "review_sample_count": 1,
                        "product_url": meta.get("product_url", ""),
                    }
                else:
                    matching_products[p_name]["review_sample_count"] += 1

        sorted_products = sorted(
            matching_products.values(),
            key=lambda x: (x["review_sample_count"], x["avg_rating"]),
            reverse=True,
        )
        return sorted_products[:limit]

    except Exception as e:
        logger.warning(f"tool_search_series_candidates failed: {e}")
        return []


def tool_get_reviews(
    product_name: str,
    aspects: Optional[List[str]] = None,
    limit: int = 15,
    trace_id: str = "",
) -> List[Dict[str, Any]]:
    """특정 상품에 대한 실제 구매자 리뷰 문장들을 검색하고 BGE-Reranker로 채점하여 반환합니다.

    Args:
        product_name: 대상 상품명
        aspects: 질의 속성 목록 (예: ['발림성', '지속력'])
        limit: 최대 수집 건수 (기본: 15)
        trace_id: 요청 추적 ID

    Returns:
        List of review dictionaries with text, rating, option, and initial score.
    """
    retriever = get_retriever()
    try:
        aspect_query = " ".join(aspects) if aspects else "실제 사용 후기 장단점"
        full_query = f"{product_name} {aspect_query}"

        # Hybrid Search 실행
        results = retriever.search(
            query=full_query,
            target_name=product_name,
            top_k=limit,
            trace_id=trace_id,
        )
        return results

    except Exception as e:
        logger.warning(f"tool_get_reviews failed: {e}")
        return []

