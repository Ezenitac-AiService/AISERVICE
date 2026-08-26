from datetime import date
from typing import Any

from pilos.analysis.llm_report import build_flask_daily_signal_response
from pilos.dto.llm_report_dto import LLMReportDTO
from pilos.service.active_model_service import (
    ActiveServiceModelError,
    get_active_service_model_context,
)
from pilos.storage.llm_report_storage import (
    LLMReportGenerationPending,
    LLMReportNotFound,
    LLMReportPending,
    LLMReportStorageError,
    read_llm_report,
)


class LLMReportInferencePendingError(RuntimeError):
    pass


class LLMReportGenerationPendingError(RuntimeError):
    pass


class LLMReportNotFoundError(RuntimeError):
    pass


class LLMReportServiceError(RuntimeError):
    pass


def get_llm_report(stock_code: str, report_date: date) -> LLMReportDTO:
    try:
        context = get_active_service_model_context()
        result = read_llm_report(
            stock_code,
            report_date,
            positive_artifact_id=context.positive_artifact_id,
            negative_artifact_id=context.negative_artifact_id,
        )

    except LLMReportPending as exc:
        raise LLMReportInferencePendingError(
            "최신 문서의 활성 모델 추론이 아직 완료되지 않았습니다."
        ) from exc

    except LLMReportGenerationPending as exc:
        raise LLMReportGenerationPendingError(
            "활성 모델 추론은 완료됐지만 보고서 생성이 대기 중입니다."
        ) from exc

    except LLMReportNotFound as exc:
        raise LLMReportNotFoundError("해당 날짜의 문서가 없습니다.") from exc

    except (ActiveServiceModelError, LLMReportStorageError) as exc:
        raise LLMReportServiceError("리포트를 조회할 수 없습니다.") from exc

    return result


def get_llm_report_for_display(
    stock_code: str,
    report_date: date,
) -> dict[str, Any]:
    """저장된 보고서를 확정된 Flask 표시 계약으로 변환한다."""
    report = get_llm_report(stock_code, report_date)

    try:
        result = build_flask_daily_signal_response(report.report_json)
        result.update(
            {
                "current_supply_data_status": (
                    report.current_supply_data_status
                ),
                "current_supply_observed_at": (
                    None
                    if report.current_supply_observed_at is None
                    else report.current_supply_observed_at.isoformat()
                ),
                "report_refresh_status": _report_refresh_status(report),
            }
        )
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise LLMReportServiceError(
            "저장된 리포트의 표시 계약이 올바르지 않습니다."
        ) from exc


def _report_refresh_status(report: LLMReportDTO) -> str:
    """기존 estimated 보고서를 숨기지 않고 갱신 대기만 표시한다."""
    if report.supply_data_status != "estimated":
        return "current"
    if report.current_supply_data_status == "confirmed":
        return "pending"
    if (
        report.current_supply_data_status == "estimated"
        and report.current_supply_observed_at is not None
        and report.supply_observed_at is not None
        and report.current_supply_observed_at > report.supply_observed_at
    ):
        return "pending"
    return "current"
