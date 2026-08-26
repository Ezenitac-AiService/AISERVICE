"""
Async MySQL Connection Pool Singleton (Spec 030 FR-026).
aiomysql.create_pool 기반 비동기 커넥션 풀로 커넥션 누수 원천 차단.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

from .config import get_settings
from .logger import get_logger, get_trace_id

logger = get_logger("oliview.db")

# ──────────────────────────────────────────────────────────────────────────────
# Global Pool Singleton
# ──────────────────────────────────────────────────────────────────────────────
_pool = None
_pool_lock = asyncio.Lock()


async def get_pool():
    """전역 aiomysql 커넥션 풀 싱글톤을 반환합니다. (Lazy initialization)"""
    global _pool
    if _pool is not None and not _pool.closed:
        return _pool

    async with _pool_lock:
        # 이중 체크 (Double-check locking)
        if _pool is not None and not _pool.closed:
            return _pool

        try:
            import aiomysql
        except ImportError:
            logger.warning(
                "aiomysql 패키지가 설치되지 않았습니다. pip install aiomysql 실행 필요.",
                extra={"trace_id": get_trace_id()},
            )
            return None

        settings = get_settings()
        try:
            _pool = await aiomysql.create_pool(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                db=settings.db_name,
                maxsize=settings.db_pool_size,     # 최대 10개 커넥션
                minsize=1,
                charset="utf8mb4",
                autocommit=True,
                pool_recycle=settings.db_pool_recycle,
                connect_timeout=5,
            )
            logger.info(
                f"aiomysql 커넥션 풀 생성 완료 (maxsize={settings.db_pool_size})",
                extra={"trace_id": get_trace_id()},
            )
        except Exception as e:
            logger.error(
                f"aiomysql 커넥션 풀 생성 실패: {e}",
                extra={"trace_id": get_trace_id(), "error_type": type(e).__name__},
            )
            _pool = None

    return _pool


@asynccontextmanager
async def acquire_db_connection():
    """
    비동기 MySQL 커넥션을 안전하게 빌려 사용하는 컨텍스트 매니저.
    사용 후 자동으로 풀에 반환하여 커넥션 누수를 방지합니다.

    Usage:
        async with acquire_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM products WHERE id = %s", (pid,))
                row = await cur.fetchone()
    """
    pool = await get_pool()
    if pool is None:
        raise RuntimeError(
            "MySQL 커넥션 풀 초기화 실패. DB 연결 설정을 확인하세요."
        )

    conn = await pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)


async def close_pool():
    """애플리케이션 종료 시 풀 정리."""
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.close()
        await _pool.wait_closed()
        logger.info("aiomysql 커넥션 풀 종료 완료")
        _pool = None
