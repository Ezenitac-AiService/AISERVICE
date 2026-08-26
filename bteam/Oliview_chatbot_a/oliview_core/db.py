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
    """Fetches review metadata (product name, brand, rating, url, text) for given review IDs."""
    if not review_ids:
        return {}

    id_list_str = ",".join(str(int(i)) for i in review_ids)
    query = f"""
    SELECT 
        r.review_id,
        r.product_id,
        p.product_name,
        p.brand,
        p.category,
        p.product_url,
        r.review_clean_text,
        r.review_text,
        r.sentiment
    FROM reviews r
    LEFT JOIN products p ON r.product_id = p.product_id
    WHERE r.review_id IN ({id_list_str})
    """
    results: Dict[int, Dict[str, Any]] = {}
    try:
        with get_db_cursor() as cursor:
            cursor.execute(query)
            for row in cursor.fetchall():
                results[row["review_id"]] = row
    except Exception as e:
        print(f"[WARN] DB 리뷰 메타데이터 조회 오류: {e}")
    return results
