import logging

import pandas as pd
from pilos.analysis.tokenizer_settings import (
    TOKENIZER_VERSION,
)
from pilos.analysis.tokenizer import (
    create_current_kiwi,
    tokenize_comments_for_current_model,
)
from pilos.storage.tokenize_db import (
    select_untokenized_comment_batch,
    insert_tokenized_comments,
)


logger = logging.getLogger(__name__)

# 기존 작업 경계의 주입 지점을 유지하면서 현재 토큰 계약 생성기를 사용한다.
create_kiwi = create_current_kiwi

SELECT_BATCH_SIZE = 2_000
NUM_WORKERS = -1

# CLI :
# uv run python -m pilos.jobs.tokenize_comments

def run_comment_tokenization(
    records:list[dict],
    tokenizer,
) -> pd.DataFrame:
    """전처리 댓글 파일 하나를 토큰화하고 저장한다."""

    processed_df = pd.DataFrame(
        records
    )

    tokenized_df = tokenize_comments_for_current_model(
        dataframe=processed_df,
        tokenizer=tokenizer,
    )


    return tokenized_df


def run_pending_comment_tokenization(
) -> int:
    """
    미토큰화 댓글을 배치 단위로 처리하고 전체 적재 건수를 반환한다.

    조회·토큰화·적재 중 실패하면 예외를 호출자에게 전달하여 후속 실행을
    중단할 수 있게 한다.
    """
    kiwi = create_kiwi(num_workers=NUM_WORKERS)
    after_id = 0
    total_inserted_count = 0

    while True:
        batch_last_id = None
        batch_count = 0

        try:
            preprocessed_comments = select_untokenized_comment_batch(
                after_id=after_id,
                batch_size=SELECT_BATCH_SIZE,
                tokenizer_version=TOKENIZER_VERSION,
            )

            if not preprocessed_comments:
                break

            batch_count = len(preprocessed_comments)
            batch_last_id = preprocessed_comments[-1][
                "preprocessed_comment_id"
            ]

            logger.info(
                "토큰화 배치 시작: "
                "after_id=%d, batch_last_id=%d, count=%d",
                after_id,
                batch_last_id,
                batch_count,
            )

            tokenized_df = run_comment_tokenization(
                records=preprocessed_comments,
                tokenizer=kiwi,
            )

            inserted_count = insert_tokenized_comments(
                tokenized_df=tokenized_df,
                tokenizer_version=TOKENIZER_VERSION,
            )

            if inserted_count != len(tokenized_df):
                raise RuntimeError(
                    "토큰화 결과 일부가 저장되지 않았습니다: "
                    f"expected={len(tokenized_df)}, "
                    f"inserted={inserted_count}"
                )

            total_inserted_count += inserted_count

            logger.info(
                "토큰화 배치 적재 완료: "
                "batch_last_id=%d, count=%d, total_count=%d",
                batch_last_id,
                inserted_count,
                total_inserted_count,
            )

            after_id = batch_last_id

        except Exception:
            logger.exception(
                "토큰화 배치 처리 실패: "
                "after_id=%d, batch_last_id=%s, count=%d",
                after_id,
                batch_last_id,
                batch_count,
            )
            raise

    return total_inserted_count


def main() -> None:
    total_count = run_pending_comment_tokenization()

    logger.info(
        "전체 토큰화 완료: %d건",
        total_count,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )
    main()
