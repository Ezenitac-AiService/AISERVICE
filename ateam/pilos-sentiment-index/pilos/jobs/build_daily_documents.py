import logging

from pilos.storage.daily_document_db import (
    select_tokenized_comments_for_day,
    select_pending_daily_document_targets,
    insert_daily_document_with_comments,
)

from pilos.analysis.daily_dataset import (
    create_daily_document_data,
    MARKET_CLOSE_TIME
)

from pilos.analysis.tokenizer_settings import (
    TOKENIZER_VERSION
)
from pilos.model_config import (
    SERVICE_INFERENCE_START_DATE
)

logger = logging.getLogger(__name__)



# CLI :
# uv run python -m pilos.jobs.build_daily_documents

def run_daily_document_building(
    *,
    min_date = SERVICE_INFERENCE_START_DATE,
) -> tuple[int,int]:
    """
    일별 모델 입력 문서를 생성하고 성공 수와 실패 수를 반환한다.

    개별 대상의 실패는 기록한 뒤 다음 대상을 계속 처리한다. 호출자는
    실패 수가 0보다 크면 후속 실행을 중단해야 한다.
    """

    targets = select_pending_daily_document_targets(
        tokenizer_version=TOKENIZER_VERSION,
        market_close_time=MARKET_CLOSE_TIME,
        min_date=min_date,
    )


    logger.info(
        "일별 문서 생성 대상: %d건",
        len(targets),
    )

    total_count = 0
    failed_count = 0

    for target in targets:
        stock_id = target["stock_id"]
        model_date = target["model_date"]

        try:
            tokenized_comments = (
                select_tokenized_comments_for_day(
                    stock_id=stock_id,
                    model_date=model_date,
                    tokenizer_version=TOKENIZER_VERSION,
                    market_close_time=MARKET_CLOSE_TIME,
                )
            )

            if not tokenized_comments:
                logger.warning(
                    "토큰화 댓글 없음: stock_id=%s, model_date=%s",
                    stock_id,
                    model_date,
                )
                continue

            daily_document_data, mapping_records = (
                create_daily_document_data(
                    stock_id=stock_id,
                    model_date=model_date,
                    tokenizer_version=TOKENIZER_VERSION,
                    records=tokenized_comments,
                )
            )

            daily_document_id = (
                insert_daily_document_with_comments(
                    daily_document_data=daily_document_data,
                    mapping_records=mapping_records,
                )
            )

            total_count += 1

            logger.info(
                "일별 문서 적재 완료: daily_document_id=%s, "
                "stock_id=%s, model_date=%s, comment_count=%d",
                daily_document_id,
                stock_id,
                model_date,
                len(mapping_records),
            )

        except Exception:
            failed_count += 1

            logger.exception(
                "일별 문서 생성 실패: stock_id=%s, model_date=%s",
                stock_id,
                model_date,
            )


    return total_count,failed_count

def main() -> None:
    total_count,failed_count = run_daily_document_building()

    logger.info(
        "일별 문서 생성 종료: 성공=%d건, 실패=%d건",
        total_count,
        failed_count,
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
