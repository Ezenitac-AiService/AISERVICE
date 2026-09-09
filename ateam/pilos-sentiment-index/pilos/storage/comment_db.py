"""댓글 수집 대상과 원본 파일 메타데이터를 MySQL에서 조회·저장한다."""

import logging

from sqlalchemy import text

from pilos.storage.db import get_engine

logger = logging.getLogger(__name__)

SELECT_STOCKS = text(
    "SELECT stock_id, stock_name, stock_subject_id FROM stock"
)

UPSERT_SOURCE_COMMENT_FILE = text(
    """
    INSERT INTO source_comment_file
        (stock_id, file_name, file_path, platform, file_ext)
    VALUES
        (:stock_id, :file_name, :file_path, :platform, :file_ext)
    ON DUPLICATE KEY UPDATE
        stock_id = VALUES(stock_id),
        file_name = VALUES(file_name),
        file_path = VALUES(file_path),
        platform = VALUES(platform),
        file_ext = VALUES(file_ext)
    """
)


class CommentDB:
    """댓글 수집에 필요한 DB 조회와 원본 파일 등록을 제공한다."""

    def __init__(self, engine=None):
        self._engine = engine or get_engine()

    def select_stock(self):
        with self._engine.connect() as connection:
            rows = connection.execute(SELECT_STOCKS).fetchall()
        logger.debug("수집 대상 종목 %d건 조회", len(rows))
        return rows

    def insert_source(self, file_source: dict) -> int:
        """원본 파일 메타데이터를 멱등 등록한다."""

        if not file_source:
            return 0
        with self._engine.begin() as connection:
            result = connection.execute(
                UPSERT_SOURCE_COMMENT_FILE,
                file_source,
            )
        logger.debug("원본 파일 메타데이터 %d행 반영", result.rowcount)
        return result.rowcount


class CommentDBUnavailableError(RuntimeError):
    """댓글 수집에 필수인 DB 연결을 확보하지 못했다."""


def require_connection(enabled: bool = True) -> CommentDB:
    """사용 가능한 댓글 수집 DB adapter를 반환한다."""

    if not enabled:
        raise CommentDBUnavailableError(
            "DB 사용이 비활성화돼 수집 대상 종목을 조회할 수 없습니다."
        )
    try:
        return CommentDB()
    except Exception as exc:
        logger.exception("DB 초기화 실패")
        raise CommentDBUnavailableError(
            "DB 접속을 확보하지 못했습니다. 저장소 루트 .env의 "
            "DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME을 확인하세요."
        ) from exc
