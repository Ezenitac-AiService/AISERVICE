import json
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from pilos.storage.db import get_engine
from pilos.dto.keyword_contribution_dto import KeywordContributionDTO
from pilos.dto.sentiment_index_dto import SentimentIndexDTO
from pilos.dto.model_result_dto import ModelResultDTO

logger = logging.getLogger(__name__)

class SentimentIndexStorageError(RuntimeError,SQLAlchemyError,ValueError):
    pass

_SELECT_LATEST_SENTIMENT_INDEXES = text(
    """
    SELECT
        s.stock_code,
        s.stock_name,
        d.model_date,
        d.comment_count,

        sd.supply_demand_index AS actual_supply_demand_index,
        sd.buy_volume AS actual_buy_volume,
        sd.sell_volume AS actual_sell_volume,
        sd.data_status AS supply_data_status,
        sd.observed_at AS supply_observed_at,

        pos.artifact_id AS positive_artifact_id,
        pos.supply_demand_association_score AS positive_supply_demand_association_score,
        pos.intercept AS positive_intercept,
        pos.text_score AS positive_text_score,
        pos.comment_count_contribution AS positive_comment_count_contribution,
        pos.recognized_feature_count AS positive_recognized_feature_count,
        pos.unique_token_count AS positive_unique_token_count,
        pos.vocabulary_coverage AS positive_vocabulary_coverage,
        pos.inference_status AS positive_inference_status,
        pos.positive_contribution_keywords AS positive_model_positive_keywords,
        pos.negative_contribution_keywords AS positive_model_negative_keywords,
        positive_artifact.model_variant AS positive_model_variant,

        neg.artifact_id AS negative_artifact_id,
        neg.supply_demand_association_score AS negative_supply_demand_association_score,
        neg.intercept AS negative_intercept,
        neg.text_score AS negative_text_score,
        neg.comment_count_contribution AS negative_comment_count_contribution,
        neg.recognized_feature_count AS negative_recognized_feature_count,
        neg.unique_token_count AS negative_unique_token_count,
        neg.vocabulary_coverage AS negative_vocabulary_coverage,
        neg.inference_status AS negative_inference_status,
        neg.positive_contribution_keywords AS negative_model_positive_keywords,
        neg.negative_contribution_keywords AS negative_model_negative_keywords,
        negative_artifact.model_variant AS negative_model_variant

    FROM stock s

    LEFT JOIN daily_document d
        ON d.daily_document_id = (
            SELECT d2.daily_document_id
            FROM daily_document d2
            WHERE d2.stock_id = s.stock_id
            ORDER BY d2.model_date DESC, d2.daily_document_id DESC
            LIMIT 1
        )

    LEFT JOIN supply_demand sd
        ON sd.stock_id = d.stock_id
        AND sd.trade_date = d.model_date

    LEFT JOIN sentiment_index_result pos
        ON pos.daily_document_id = d.daily_document_id
       AND pos.artifact_id = :positive_artifact_id

    LEFT JOIN sentiment_index_result neg
        ON neg.daily_document_id = d.daily_document_id
       AND neg.artifact_id = :negative_artifact_id

    LEFT JOIN artifacts positive_artifact
        ON positive_artifact.artifact_id = pos.artifact_id
       AND positive_artifact.model_variant = 'positive'

    LEFT JOIN artifacts negative_artifact
        ON negative_artifact.artifact_id = neg.artifact_id
       AND negative_artifact.model_variant = 'negative'

    ORDER BY s.stock_code ASC
    """
)

_SELECT_DETAIL_SENTIMENT_INDEXES_BY_STOCK_CODE = text(
    """
    SELECT
        s.stock_code,
        s.stock_name,
        d.model_date,
        d.comment_count,

        sd.supply_demand_index AS actual_supply_demand_index,
        sd.buy_volume AS actual_buy_volume,
        sd.sell_volume AS actual_sell_volume,
        sd.data_status AS supply_data_status,
        sd.observed_at AS supply_observed_at,

        pos.artifact_id AS positive_artifact_id,
        positive_artifact.model_variant AS positive_model_variant,
        pos.supply_demand_association_score AS positive_supply_demand_association_score,
        pos.intercept AS positive_intercept,
        pos.text_score AS positive_text_score,
        pos.comment_count_contribution
            AS positive_comment_count_contribution,
        pos.recognized_feature_count
            AS positive_recognized_feature_count,
        pos.unique_token_count AS positive_unique_token_count,
        pos.vocabulary_coverage AS positive_vocabulary_coverage,
        pos.inference_status AS positive_inference_status,
        pos.positive_contribution_keywords
            AS positive_model_positive_keywords,
        pos.negative_contribution_keywords
            AS positive_model_negative_keywords,

        neg.artifact_id AS negative_artifact_id,
        negative_artifact.model_variant AS negative_model_variant,
        neg.supply_demand_association_score
            AS negative_supply_demand_association_score,
        neg.intercept AS negative_intercept,
        neg.text_score AS negative_text_score,
        neg.comment_count_contribution
            AS negative_comment_count_contribution,
        neg.recognized_feature_count
            AS negative_recognized_feature_count,
        neg.unique_token_count AS negative_unique_token_count,
        neg.vocabulary_coverage AS negative_vocabulary_coverage,
        neg.inference_status AS negative_inference_status,
        neg.positive_contribution_keywords
            AS negative_model_positive_keywords,
        neg.negative_contribution_keywords
            AS negative_model_negative_keywords

    FROM daily_document d

    JOIN stock s
        ON s.stock_id = d.stock_id

    LEFT JOIN supply_demand sd
        ON sd.stock_id = d.stock_id
        AND sd.trade_date = d.model_date

    LEFT JOIN sentiment_index_result pos
        ON pos.daily_document_id = d.daily_document_id
       AND pos.artifact_id = :positive_artifact_id

    LEFT JOIN artifacts positive_artifact
        ON positive_artifact.artifact_id = pos.artifact_id
       AND positive_artifact.model_variant = 'positive'

    LEFT JOIN sentiment_index_result neg
        ON neg.daily_document_id = d.daily_document_id
       AND neg.artifact_id = :negative_artifact_id

    LEFT JOIN artifacts negative_artifact
        ON negative_artifact.artifact_id = neg.artifact_id
       AND negative_artifact.model_variant = 'negative'

    WHERE s.stock_code = :stock_code
      AND NOT EXISTS (
          SELECT 1
          FROM daily_document newer_document
          WHERE newer_document.stock_id = d.stock_id
            AND newer_document.model_date = d.model_date
            AND (
                (EXISTS (SELECT 1 FROM sentiment_index_result sir WHERE sir.daily_document_id = newer_document.daily_document_id)
                 AND NOT EXISTS (SELECT 1 FROM sentiment_index_result sir2 WHERE sir2.daily_document_id = d.daily_document_id))
                OR
                (EXISTS (SELECT 1 FROM sentiment_index_result sir WHERE sir.daily_document_id = newer_document.daily_document_id) =
                 EXISTS (SELECT 1 FROM sentiment_index_result sir2 WHERE sir2.daily_document_id = d.daily_document_id)
                 AND newer_document.daily_document_id > d.daily_document_id)
            )
      )

    ORDER BY
        d.model_date DESC,
        d.daily_document_id DESC
    """
)

# 긍/부정 키워드 하나씩 꺼내기
def convert_keyword_row(keyword_row: object) -> tuple[KeywordContributionDTO, ...]:
    if keyword_row is None:
        return ()

    if isinstance(keyword_row, str):
        try: 
            keyword_row = json.loads(keyword_row)
        except json.JSONDecodeError as err:
            raise ValueError("키워드 컬럼이 올바른 json이 아님") from err

    if not isinstance(keyword_row, list):
        raise TypeError("키워드 컬럼은 JSON 배열이어야 합니다.")

    converted_keywords: list[KeywordContributionDTO] = []

    for keyword_record in keyword_row:
        if not isinstance(keyword_record, dict):
            raise TypeError("키워드 항목은 JSON 객체여야 합니다.")
        
        word = keyword_record.get("word")
        contribution = keyword_record.get("contribution")

        converted_keywords.append(
            KeywordContributionDTO(
                keyword=word.strip(),
                contribution=float(contribution),
            )
        )
    return tuple(converted_keywords)

# result 반환
def convert_model_result(row, prefix: str) -> ModelResultDTO | None:
    if row[f"{prefix}_artifact_id"] is None:
        return None

    return ModelResultDTO(
        artifact_id=int(row[f"{prefix}_artifact_id"]),
        model_variant=str(row[f"{prefix}_model_variant"]),
        supply_demand_association_score=float(row[f"{prefix}_supply_demand_association_score"]),
        intercept=float(row[f"{prefix}_intercept"]),
        text_score=float(row[f"{prefix}_text_score"]),
        comment_count_contribution=float(row[f"{prefix}_comment_count_contribution"]),
        recognized_feature_count=int(row[f"{prefix}_recognized_feature_count"]),
        unique_token_count=(
            int(row[f"{prefix}_unique_token_count"])
            if row[f"{prefix}_unique_token_count"] is not None
            else None
        ),
        vocabulary_coverage=(
            float(row[f"{prefix}_vocabulary_coverage"])
            if row[f"{prefix}_vocabulary_coverage"] is not None
            else None
        ),
        inference_status=(
            str(row[f"{prefix}_inference_status"])
            if row[f"{prefix}_inference_status"] is not None
            else None
        ),
        positive_keywords=convert_keyword_row(row[f"{prefix}_model_positive_keywords"]),
        negative_keywords=convert_keyword_row(row[f"{prefix}_model_negative_keywords"]),
    )

# DTO로 변환
def convert_row_to_dto(row: object) -> SentimentIndexDTO:
    stock_code = str(row["stock_code"]).zfill(6)
    if not isinstance(stock_code, str) or not stock_code.strip():
        raise ValueError(f"stock_code가 올바르지 않습니다.")
    
    return SentimentIndexDTO(
        stock_code = stock_code,
        stock_name=str(row["stock_name"]),
        model_date=row["model_date"],
        comment_count=(
            int(row["comment_count"])
            if row["comment_count"] is not None
            else None
        ),
        positive_model=convert_model_result(row, "positive"),
        negative_model=convert_model_result(row, "negative"),
        actual_supply_demand_index=(
            float(row["actual_supply_demand_index"])
            if row["actual_supply_demand_index"] is not None
            else None
        ),
        actual_buy_volume=(
            int(row["actual_buy_volume"])
            if row["actual_buy_volume"] is not None
            else None
        ),
        actual_sell_volume=(
            int(row["actual_sell_volume"])
            if row["actual_sell_volume"] is not None
            else None
        ),
        supply_data_status=(
            str(row["supply_data_status"])
            if row["supply_data_status"] is not None
            else None
        ),
        supply_observed_at=row["supply_observed_at"],
        analysis_status=None,
    )

# 메인) 최신 데이터 꺼내기
def read_latest_sentiment_indexes(
    pos_artifact_id: int,
    neg_artifact_id: int,
) -> list[SentimentIndexDTO]:
    try: 
        engine = get_engine() 
        with engine.connect() as conn:
            rows = conn.execute(_SELECT_LATEST_SENTIMENT_INDEXES,{
                "positive_artifact_id": pos_artifact_id,
                "negative_artifact_id": neg_artifact_id,
            },).mappings().all()
        return [convert_row_to_dto(row) for row in rows]
    
    except (SQLAlchemyError, RuntimeError, ValueError) as err:
        logger.exception("db조회 실패")
        raise SentimentIndexStorageError("조회 할 수 없습니다.") from err
    

# 디테일) 종목별 데이터 꺼내기
def read_sentiment_indexes_by_stock_code(stock_code: str, pos_artifact_id: int, neg_artifact_id) -> list[SentimentIndexDTO]:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(_SELECT_DETAIL_SENTIMENT_INDEXES_BY_STOCK_CODE,{
                "stock_code": stock_code,
                "positive_artifact_id": pos_artifact_id,
                "negative_artifact_id": neg_artifact_id,
                }).mappings().all()
        return [convert_row_to_dto(row) for row in rows]
    
    except (SQLAlchemyError, RuntimeError, ValueError) as err:
        logger.exception("db조회 실패")
        raise SentimentIndexStorageError("조회 할 수 없습니다.") from err
