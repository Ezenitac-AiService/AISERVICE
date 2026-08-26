import json
import pandas as pd

from sqlalchemy import text

from pilos.storage.db import get_engine

INSERT_BATCH_SIZE = 500


def select_untokenized_comment_batch(
    *,
    after_id: int,
    batch_size: int,
    tokenizer_version: str,
) -> list[dict]:
    """
    지정한 ID 이후의 미토큰화 전처리 댓글을 한 청크 반환한다.
    현재 토크나이저 버전으로 만든 결과가 없으면
    다시 토큰화 대상으로 조회한다.
    """
    if after_id < 0:
        raise ValueError("after_id는 0 이상이어야 합니다.")

    if batch_size <= 0:
        raise ValueError("batch_size는 1 이상이어야 합니다.")

    if not tokenizer_version.strip():
        raise ValueError("tokenizer_version은 비어 있을 수 없습니다.")

    sql = text("""
        SELECT
            pc.preprocessed_comment_id,
            pc.text
        FROM preprocessed_comment AS pc
        WHERE pc.preprocessed_comment_id > :after_id
          AND NOT EXISTS (
              SELECT 1
              FROM tokenized_comment AS tc
              WHERE tc.preprocessed_comment_id
                    = pc.preprocessed_comment_id
                AND tc.tokenizer_version
                    = :tokenizer_version
          )
        ORDER BY pc.preprocessed_comment_id
        LIMIT :batch_size
    """)

    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            sql,
            {
                "after_id": after_id,
                "batch_size": batch_size,
                "tokenizer_version": tokenizer_version,
            },
        )

        return [
            dict(row)
            for row in result.mappings()
        ]

def insert_tokenized_comments(
    tokenized_df: pd.DataFrame,
    tokenizer_version: str,
) -> int:
    """
    토큰화 완료된 데이터를 적재한다.
    """
    sql = text("""
        INSERT INTO tokenized_comment (
            preprocessed_comment_id,
            tokens,
            tokenizer_version
        )
        VALUES (
            :preprocessed_comment_id,
            :tokens,
            :tokenizer_version
        )
        """)
    engine = get_engine()
    total_inserted_count = 0
    with engine.begin() as conn:
        for start in range(
            0,
            len(tokenized_df),
            INSERT_BATCH_SIZE,
        ):
            insert_chunk = tokenized_df.iloc[
                start:start + INSERT_BATCH_SIZE
            ]
            records = [
                {
                    "preprocessed_comment_id": (
                        row.preprocessed_comment_id
                    ),
                    "tokens": json.dumps(
                        row.kiwi_tokens,
                        ensure_ascii=False,
                    ),
                    "tokenizer_version": tokenizer_version,
                }
                for row in insert_chunk.itertuples(index=False)
            ]
            result = conn.execute(sql, records)
            total_inserted_count += result.rowcount

    return total_inserted_count
