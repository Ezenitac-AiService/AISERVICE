import json
import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from pilos.dto.llm_report_dto import (
    EVIDENCE_SCHEMA_VERSION,
    LLMReportDTO,
    PROMPT_VERSION,
    REPORT_SCHEMA_VERSION,
)
from pilos.storage.db import get_engine


logger = logging.getLogger(__name__)

class LLMReportPending(RuntimeError):
    """최신 문서의 선행 추론 결과가 아직 없는 상태."""
class LLMReportNotFound(RuntimeError):
    """요청한 종목·날짜의 최신 일별문서가 없는 상태."""
class LLMReportGenerationPending(RuntimeError):
    """추론은 완료됐지만 현재 v13 보고서가 아직 없는 상태."""
class LLMReportStorageError(RuntimeError,SQLAlchemyError,ValueError):
    pass

# 최신 문서 조회
_SELECT_LATEST_DOCUMENT = text(
    """
    SELECT d.daily_document_id

    FROM daily_document d

    JOIN stock s
        ON s.stock_id = d.stock_id

    WHERE s.stock_code = :stock_code
      AND d.model_date = :model_date

    ORDER BY
      EXISTS (SELECT 1 FROM llm_report lr WHERE lr.daily_document_id = d.daily_document_id) DESC,
      EXISTS (SELECT 1 FROM sentiment_index_result sir WHERE sir.daily_document_id = d.daily_document_id) DESC,
      d.daily_document_id DESC
    LIMIT 1
    """
)

# 최신 문서의 보고서 조회
_SELECT_LLM_REPORT = text(
    """
    SELECT
        lr.*,
        s.stock_code,
        dd.comment_count,
        sd.data_status AS current_supply_data_status,
        sd.observed_at AS current_supply_observed_at

    FROM llm_report lr

    JOIN stock s
        ON s.stock_id = lr.stock_id
    JOIN daily_document dd
        ON dd.daily_document_id = lr.daily_document_id
    LEFT JOIN supply_demand sd
        ON sd.stock_id = dd.stock_id
       AND sd.trade_date = dd.model_date

    WHERE lr.daily_document_id = :daily_document_id
      AND lr.prompt_version = :prompt_version
      AND lr.report_schema_version = :report_schema_version
      AND lr.evidence_schema_version = :evidence_schema_version
      AND lr.positive_result_id = (
          SELECT sir.sentiment_index_result_id
          FROM sentiment_index_result sir
          WHERE sir.daily_document_id = :daily_document_id
            AND sir.artifact_id = :positive_artifact_id
      )
      AND lr.negative_result_id = (
          SELECT sir.sentiment_index_result_id
          FROM sentiment_index_result sir
          WHERE sir.daily_document_id = :daily_document_id
            AND sir.artifact_id = :negative_artifact_id
      )

    ORDER BY
        lr.created_at DESC,
        lr.llm_report_id DESC
    LIMIT 1
    """
)

# 보고서가 없을 때 선행 추론 확인
_SELECT_INFERENCE_VARIANTS = text(
    """
    SELECT DISTINCT sir.artifact_id
    FROM sentiment_index_result sir
    WHERE sir.daily_document_id = :daily_document_id
      AND sir.artifact_id IN (
          :positive_artifact_id,
          :negative_artifact_id
      )
    """
)

def parse_report_json(value: object) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("report_json이 올바른 JSON이 아닙니다.") from exc

    if not isinstance(value, dict):
        raise TypeError(
            "report_json은 JSON 객체여야 합니다."
        )
    return value

def convert_row_to_dto(row) -> LLMReportDTO:
    return LLMReportDTO(
        llm_report_id=int(row["llm_report_id"]),
        stock_id=int(row["stock_id"]),
        stock_code=str( row["stock_code"]).zfill(6),
        model_date=row["model_date"],
        daily_document_id=int(row["daily_document_id"]),
        comment_count=int(row["comment_count"]),
        positive_result_id=int(row["positive_result_id"]),
        negative_result_id=int(row["negative_result_id"]),
        provider=str(row["provider"]),
        model=str(row["model"]),
        prompt_version=str(row["prompt_version"]),
        report_schema_version=int(row["report_schema_version"]),
        evidence_schema_version=int(row["evidence_schema_version"]),
        status=str(row["status"]),
        report_json=parse_report_json(row["report_json"]),
        input_hash=str(row["input_hash"]),
        provider_response_id=(
            str(row["provider_response_id"])
            if row["provider_response_id"] is not None
            else None
        ),
        input_tokens=(
            int(row["input_tokens"])
            if row["input_tokens"] is not None
            else None
        ),
        output_tokens=(
            int(row["output_tokens"])
            if row["output_tokens"] is not None
            else None
        ),
        created_at=row["created_at"],
        supply_data_status=(
            str(row["supply_data_status"])
            if row["supply_data_status"] is not None
            else None
        ),
        supply_observed_at=row["supply_observed_at"],
        current_supply_data_status=(
            str(row["current_supply_data_status"])
            if row["current_supply_data_status"] is not None
            else None
        ),
        current_supply_observed_at=row["current_supply_observed_at"],
    )

def read_llm_report(
    stock_code: str,
    model_date: date,
    *,
    positive_artifact_id: int,
    negative_artifact_id: int,
) -> LLMReportDTO:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            doc = conn.execute(
                _SELECT_LATEST_DOCUMENT,{
                    "stock_code": stock_code, 
                    "model_date": model_date},
                ).mappings().first()

            if doc is None:
                raise LLMReportNotFound("해당 날짜의 일별문서가 없습니다.")

            daily_document_id = int(doc["daily_document_id"])

            report = conn.execute(
                _SELECT_LLM_REPORT,
                {
                    "daily_document_id": daily_document_id,
                    "prompt_version": PROMPT_VERSION,
                    "report_schema_version": REPORT_SCHEMA_VERSION,
                    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                    "positive_artifact_id": positive_artifact_id,
                    "negative_artifact_id": negative_artifact_id,
                },
            ).mappings().first()
            
            if report is not None:
                return convert_row_to_dto(report)

            artifact_ids = conn.execute(
                _SELECT_INFERENCE_VARIANTS,
                {
                    "daily_document_id": daily_document_id,
                    "positive_artifact_id": positive_artifact_id,
                    "negative_artifact_id": negative_artifact_id,
                },
            ).scalars().all()

            inference_ready = {
                positive_artifact_id,
                negative_artifact_id,
            }.issubset(set(artifact_ids))

            if not inference_ready:
                raise LLMReportPending(
                    "최신 문서의 양·음수 추론이 "
                    "아직 완료되지 않았습니다."
                )
            raise LLMReportGenerationPending(
                "현재 v13 보고서가 아직 생성되지 않았습니다."
            )

    except (
        LLMReportPending,
        LLMReportNotFound,
        LLMReportGenerationPending,
    ):
        raise

    except (
        SQLAlchemyError,
        RuntimeError,
        TypeError,
        ValueError,
        KeyError,
    ) as exc:
        logger.exception("LLM 리포트 DB 조회 실패")
        raise LLMReportStorageError("LLM 리포트를 조회할 수 없습니다.") from exc
