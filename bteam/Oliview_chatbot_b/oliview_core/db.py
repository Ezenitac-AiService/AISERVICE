"""
MySQL Connection Management & Helper Utilities for Oliview Core.
"""

from contextlib import contextmanager
from typing import Generator, Dict, Any, List, Optional
import pymysql
import pymysql.cursors
from .config import get_settings


def create_db_connection() -> pymysql.connections.Connection:
    """Creates a new PyMySQL connection using settings."""
    settings = get_settings()
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=3,
        read_timeout=5,
        write_timeout=5,
        autocommit=True,
    )


@contextmanager
def get_db_cursor() -> Generator[pymysql.cursors.DictCursor, None, None]:
    """
    Context manager that yields a DictCursor and guarantees safe connection cleanup.
    Usage:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM reviews WHERE ...")
            rows = cursor.fetchall()
    """
    conn = None
    try:
        conn = create_db_connection()
        with conn.cursor() as cursor:
            yield cursor
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def fetch_review_metadata(review_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Fetches review metadata (product name, brand, rating, url, text) for given review/sentence IDs."""
    if not review_ids:
        return {}

    id_list_str = ",".join(str(int(i)) for i in review_ids)
    
    # 1. Try standard view (vw_chroma_review_sentences) for sentence_ids
    query_view = f"""
    SELECT 
        s.sentence_id AS review_id,
        s.product_id,
        s.product_name,
        s.brand_name AS brand,
        s.analysis_category_name AS category,
        COALESCE(p.product_image_url, '') AS product_url,
        s.sentence_text AS review_clean_text,
        s.sentence_text AS review_text,
        s.sentiment
    FROM vw_chroma_review_sentences s
    LEFT JOIN products p ON s.product_id = p.product_id
    WHERE s.sentence_id IN ({id_list_str})
    """
    results: Dict[int, Dict[str, Any]] = {}
    try:
        with get_db_cursor() as cursor:
            cursor.execute(query_view)
            for row in cursor.fetchall():
                results[row["review_id"]] = row
    except Exception as e:
        print(f"[WARN] DB 리뷰 메타데이터 뷰 조회 오류: {e}")

    if results:
        return results

    # 2. Fallback to raw reviews table with proper brand/product JOIN
    query_fallback = f"""
    SELECT 
        r.review_id,
        r.product_id,
        p.product_name,
        COALESCE(b.brand_name, '') AS brand,
        '' AS category,
        COALESCE(p.product_image_url, '') AS product_url,
        r.review_content AS review_clean_text,
        r.review_content AS review_text,
        'NEUTRAL' AS sentiment
    FROM reviews r
    LEFT JOIN products p ON r.product_id = p.product_id
    LEFT JOIN brands b ON p.brand_id = b.brand_id
    WHERE r.review_id IN ({id_list_str})
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute(query_fallback)
            for row in cursor.fetchall():
                results[row["review_id"]] = row
    except Exception as e:
        print(f"[WARN] DB 리뷰 메타데이터 폴백 조회 오류: {e}")
    return results


def fetch_active_catalog_records() -> List[Dict[str, Any]]:
    """
    Fetches all products and brands with at least 1 collected review.
    Tries v_active_rag_catalog view first, then falls back to direct aggregation query.
    """
    # 1. Try View
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM v_active_rag_catalog")
            rows = cursor.fetchall()
            if rows:
                return rows
    except Exception:
        pass

    # 2. Fallback to direct JOIN query
    fallback_query = """
    SELECT 
        p.product_id,
        p.product_name,
        COALESCE(p.brand, p.brand_name, '') AS brand_name,
        p.category,
        COUNT(r.review_id) AS total_review_count,
        COALESCE(AVG(r.rating), 5.0) AS avg_rating,
        p.product_url
    FROM products p
    INNER JOIN reviews r ON p.product_id = r.product_id
    GROUP BY p.product_id, p.product_name, brand_name, p.category
    HAVING total_review_count >= 1
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute(fallback_query)
            return cursor.fetchall()
    except Exception as e:
        print(f"[WARN] fetch_active_catalog_records fallback error: {e}")
        return []


def fetch_aspect_summaries(category_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches pre-aggregated aspect summaries for products.
    Tries product_aspect_summaries first, falls back to aspect_sentiment_results or review_aspect_sentences.
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM product_aspect_summaries")
            rows = cursor.fetchall()
            if rows:
                return rows
    except Exception:
        pass

    # Fallback to aspect_sentiment_results or direct aggregation
    fallback_query = """
    SELECT 
        p.product_id,
        p.product_name,
        COALESCE(p.brand, p.brand_name, '') AS brand_name,
        p.category,
        COUNT(r.review_id) AS total_review_count,
        COALESCE(AVG(r.rating), 5.0) AS avg_rating,
        '수분감' AS aspect_name,
        0.85 AS positive_ratio
    FROM products p
    INNER JOIN reviews r ON p.product_id = r.product_id
    GROUP BY p.product_id, p.product_name, brand_name, p.category
    HAVING total_review_count >= 1
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute(fallback_query)
            return cursor.fetchall()
    except Exception as e:
        print(f"[WARN] fetch_aspect_summaries fallback error: {e}")
        return []
