import json

from datetime import date, datetime, time

from sqlalchemy import text

from pilos.storage.db import get_engine



def select_pending_daily_document_targets(
    *,
    tokenizer_version: str,
    market_close_time: time,
    min_date: date | None = None,
) -> list[dict]:
    """일별 문서를 다시 생성해야 하는 종목·날짜를 반환한다."""
    if not tokenizer_version.strip():
        raise ValueError(
            "tokenizer_version은 비어 있을 수 없습니다."
        )

    date_filter = ""
    params: dict = {
        "tokenizer_version": tokenizer_version,
        "market_close_time": market_close_time,
    }
    if min_date is not None:
        date_filter = "AND pc.created_at >= :min_date"
        params["min_date"] = datetime.combine(min_date, time.min)

    sql = text(f"""
        SELECT DISTINCT
            pc.stock_id,
            DATE(pc.created_at) AS model_date
        FROM preprocessed_comment AS pc
        STRAIGHT_JOIN tokenized_comment AS tc
            ON tc.preprocessed_comment_id
               = pc.preprocessed_comment_id
        WHERE tc.tokenizer_version = :tokenizer_version
          AND TIME(pc.created_at) < :market_close_time
          {date_filter}
          AND NOT EXISTS (
              SELECT 1
              FROM daily_document_comment AS ddc
              WHERE ddc.tokenized_comment_id
                    = tc.tokenized_comment_id
          )
        ORDER BY
            model_date DESC,
            pc.stock_id ASC
    """)

    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(sql, params)

        records = [
            dict(row)
            for row in result.mappings()
        ]

    return records



def select_tokenized_comments_for_day(
    *,
    stock_id: int,
    model_date: date,
    tokenizer_version: str,
    market_close_time:time,
) -> list[dict]:
    """특정 종목·날짜의 장 마감 전 토큰화 댓글을 조회한다."""
    start_at = datetime.combine(
        model_date,
        time.min,
    )
    market_close_at  = datetime.combine(
        model_date,
        market_close_time,
    )

    sql = text("""
        SELECT
            tc.tokenized_comment_id,
            tc.tokens AS kiwi_tokens,
            tc.tokenizer_version,
            pc.stock_id,
            pc.created_at
        FROM tokenized_comment AS tc
        INNER JOIN preprocessed_comment AS pc
            ON pc.preprocessed_comment_id
               = tc.preprocessed_comment_id
        WHERE pc.stock_id = :stock_id
          AND tc.tokenizer_version = :tokenizer_version
          AND pc.created_at >= :start_at
          AND pc.created_at < :market_close_at 
        ORDER BY
            pc.created_at ASC,
            tc.tokenized_comment_id ASC
    """)
       
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            sql,
            {
                "stock_id": stock_id,
                "tokenizer_version": tokenizer_version,
                "start_at": start_at,
                "market_close_at": market_close_at,
            },
        )

        records = [
            dict(row)
            for row in result.mappings()
        ]

    # text() 쿼리에서는 JSON 컬럼이 문자열로 반환될 수 있으므로
    # 분석 영역에 넘기기 전에 Python list로 변환한다.
    for record in records:
        if isinstance(record["kiwi_tokens"], str):
            record["kiwi_tokens"] = json.loads(
                record["kiwi_tokens"]
            )

    return records

def insert_daily_document_with_comments(
    *,
    daily_document_data: dict,
    mapping_records: list[dict],
) -> int:
    """일별 문서와 댓글 매핑을 한 트랜잭션으로 적재하고 문서 ID를 반환한다."""
    if not mapping_records:
        raise ValueError("매핑 데이터가 없습니다.")

    if daily_document_data["comment_count"] != len(mapping_records):
        raise ValueError(
            "문서의 댓글 수와 매핑 데이터 수가 다릅니다."
        )
    
    sql = text("""
        INSERT INTO daily_document (
            stock_id,
            model_date,
            tokenizer_version,
            tfidf_text,
            comment_count,
            document_hash
        )
        VALUES (
            :stock_id,
            :model_date,
            :tokenizer_version,
            :tfidf_text,
            :comment_count,
            :document_hash
        )
    """)
    engine = get_engine()
    with engine.begin() as conn:
        existing_id = conn.execute(
            text("""
                SELECT daily_document_id FROM daily_document
                WHERE stock_id = :stock_id
                  AND model_date = :model_date
                  AND tokenizer_version = :tokenizer_version
                  AND document_hash = :document_hash
            """),
            daily_document_data,
        ).scalar()
        if existing_id is not None:
            return int(existing_id)

        result = conn.execute(
            sql,
            daily_document_data,
        )
        daily_document_id = result.lastrowid
        sql = text("""
            INSERT INTO daily_document_comment (
                daily_document_id,
                tokenized_comment_id,
                sequence_number
            )
            VALUES (
                :daily_document_id,
                :tokenized_comment_id,
                :sequence_number
            )
        """).bindparams(
            daily_document_id = daily_document_id
        )

        result = conn.execute(
            sql,
            mapping_records,
        )
        if result.rowcount != len(mapping_records):
            raise ValueError(
                "적재된 행 수와 매핑 데이터 수가 다릅니다"
            )
    return daily_document_id
