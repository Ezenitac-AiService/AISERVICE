import argparse
import json
import logging

from collections import defaultdict
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable

from pilos.analysis.llm_report import (
    build_report_json,
    build_signal_evidence,
    calculate_report_input_hash,
    classify_supply_state,
    should_request_llm_commentary,
)
from pilos.analysis.signal_calibration import (
    build_comment_signal_history,
    build_daily_comment_signal,
    verify_calibration_matches_artifact,
)
from pilos.collection.ai_clients.llm_report_client import (
    LlmReportClient,
    LlmReportClientSettings,
    LlmReportResponseError,
    OpenAICompatibleLlmReportClient,
    load_llm_report_identity_from_env,
)
from pilos.dto.comment_signal_dto import (
    CommentSignalHistory,
    DailyCommentSignal,
    SignalCalibration,
)
from pilos.dto.llm_report_dto import (
    EVIDENCE_SCHEMA_VERSION,
    PROMPT_VERSION,
    REPORT_SCHEMA_VERSION,
    LlmMarketCommentary,
    ReportGenerationRequest,
    ReportGenerationResult,
)
from pilos.storage.llm_report_db import (
    insert_llm_report,
    resolve_history_start_date,
    select_latest_llm_report_targets,
    select_llm_report_existing_hashes,
    select_signal_history_results,
    update_v13_llm_report_for_supply_change,
)
from pilos.storage.model_artifacts import load_registered_model_artifacts
from pilos.storage.signal_calibration_store import (
    load_signal_calibration,
    resolve_calibration_path,
)


# CLI:
# uv run python -m pilos.jobs.generate_llm_reports \
#   --start-date YYYY-MM-DD --end-date YYYY-MM-DD

logger = logging.getLogger(__name__)

# 실행 로그를 남길 경로다. Git 비추적 산출물이다.
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

from pilos.model_config import (
    ACTIVE_SERVICE_MODEL_VERSION as MODEL_VERSION,
    SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION as ARTIFACT_SCHEMA_VERSION,
    SERVICE_MODEL_NAME as MODEL_NAME,
)
SUMMARY_KEYS = (
    "input_count",
    "generated_count",
    "deterministic_count",
    "existing_count",
    "updated_count",
    "not_ready_count",
    "failed_count",
)


def run_pending_llm_report_generation(
    *,
    report_start_date: date,
    report_end_date: date,
    client: LlmReportClient | None = None,
    provider: str | None = None,
    model: str | None = None,
    calibration: SignalCalibration | None = None,
    calibration_path: Path | None = None,
    select_targets: Callable[..., list[dict[str, Any]]] = (
        select_latest_llm_report_targets
    ),
    select_history: Callable[..., list[dict[str, Any]]] = (
        select_signal_history_results
    ),
    select_existing_hashes: Callable[..., list[dict[str, Any]]] = (
        select_llm_report_existing_hashes
    ),
    insert_report: Callable[..., int] = insert_llm_report,
    update_report: Callable[..., bool] = update_v13_llm_report_for_supply_change,
    load_artifacts: Callable[..., tuple[dict, dict]] = load_registered_model_artifacts,
    load_llm_identity: Callable[[], tuple[str, str]] = (
        load_llm_report_identity_from_env
    ),
) -> dict[str, int]:
    """
    최신 일별문서의 댓글 수급 신호 보고서를 생성하고 상태를 집계한다.

    LLM은 이미 계산된 정형 수치를 요약만 한다. 비교할 과거 신호가 없거나
    신호를 계산할 수 없는 날은 LLM을 호출하지 않고 deterministic 요약을
    저장한다.
    """
    if report_start_date > report_end_date:
        raise ValueError("보고서 시작일은 종료일보다 늦을 수 없습니다.")

    if calibration is None:
        calibration = load_signal_calibration(
            calibration_path
            or resolve_calibration_path(
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
            )
        )

    _validate_calibration_identity(calibration)

    for model_variant in ("positive", "negative"):
        artifact_record, _bundle = load_artifacts(
            model_name=MODEL_NAME,
            model_variant=model_variant,
            model_version=MODEL_VERSION,
            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            base_dir=Path(__file__).resolve().parents[2],
        )
        verify_calibration_matches_artifact(
            calibration=calibration,
            artifact_record=artifact_record,
        )

    target_rows = select_targets(
        report_start_date=report_start_date,
        report_end_date=report_end_date,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
    )
    targets = _group_latest_document_targets(target_rows)
    summary = {key: 0 for key in SUMMARY_KEYS}
    summary["input_count"] = len(targets)
    logger.info(
        "LLM 보고서 생성 대상: %d건, 기간=%s~%s, prompt_version=%s",
        len(targets),
        report_start_date,
        report_end_date,
        PROMPT_VERSION,
    )

    if not targets:
        return summary

    if bool(provider) != bool(model):
        raise ValueError("LLM 보고서 provider와 model은 함께 명시해야 합니다.")
    if not provider or not model:
        provider, model = load_llm_identity()

    def get_llm_client() -> LlmReportClient:
        nonlocal client
        if client is None:
            settings = LlmReportClientSettings.from_env()
            if (settings.provider, settings.model) != (provider, model):
                raise ValueError(
                    "LLM client 설정이 보고서 생성 고유키와 다릅니다."
                )
            client = OpenAICompatibleLlmReportClient(settings=settings)
        return client

    history_rows = select_history(
        stock_ids=sorted({target["stock_id"] for target in targets}),
        history_start_date=resolve_history_start_date(report_start_date),
        history_end_date=report_end_date,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
    )
    history_by_stock = _build_history_signals(
        history_rows=history_rows,
        calibration=calibration,
    )

    for target in targets:
        status = _process_target(
            target=target,
            calibration=calibration,
            previous_signals=history_by_stock.get(target["stock_id"], []),
            provider=provider,
            model=model,
            get_client=get_llm_client,
            select_existing_hashes=select_existing_hashes,
            insert_report=insert_report,
            update_report=update_report,
        )
        summary[f"{status}_count"] += 1

    _validate_summary(summary)
    logger.info(
        "LLM 보고서 생성 종료: 대상=%d건, LLM 생성=%d건, "
        "deterministic=%d건, 기존=%d건, 갱신=%d건, 미준비=%d건, 실패=%d건",
        summary["input_count"],
        summary["generated_count"],
        summary["deterministic_count"],
        summary["existing_count"],
        summary["updated_count"],
        summary["not_ready_count"],
        summary["failed_count"],
    )
    return summary


def _validate_calibration_identity(
    calibration: SignalCalibration,
) -> None:
    """calibration이 이 job이 사용하는 모델 버전과 같은지 확인한다."""
    mismatches = [
        field_name
        for field_name, expected, actual in (
            ("model_name", MODEL_NAME, calibration.model_name),
            ("model_version", MODEL_VERSION, calibration.model_version),
            (
                "artifact_schema_version",
                ARTIFACT_SCHEMA_VERSION,
                calibration.artifact_schema_version,
            ),
        )
        if expected != actual
    ]

    if mismatches:
        raise ValueError(
            "calibration이 이 job의 모델 버전과 다릅니다: "
            f"{mismatches}"
        )


def _group_latest_document_targets(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """storage의 flat join 결과를 일별문서 단위 대상 구조로 묶는다."""
    grouped: dict[int, dict[str, Any]] = {}

    for row in rows:
        daily_document_id = int(row["daily_document_id"])
        target = grouped.setdefault(
            daily_document_id,
            {
                "daily_document_id": daily_document_id,
                "stock_id": int(row["stock_id"]),
                "stock_code": str(row["stock_code"]).zfill(6),
                "stock_name": row["stock_name"],
                "model_date": row["model_date"],
                "comment_count": int(row["comment_count"]),
                "actual_supply_index": row["actual_supply_index"],
                "supply_data_status": row["supply_data_status"],
                "supply_observed_at": row["supply_observed_at"],
                "results_by_variant": {},
                "duplicate_variants": set(),
            },
        )
        model_variant = row.get("model_variant")
        result_id = row.get("sentiment_index_result_id")

        if model_variant not in {"positive", "negative"} or result_id is None:
            continue

        # 같은 방향 결과가 둘 이상이면 어느 행이 정본인지 알 수 없다.
        # 전체 실행을 중단하지 않고 해당 대상만 실패로 처리하도록
        # 여기서는 사실만 기록한다.
        if model_variant in target["results_by_variant"]:
            target["duplicate_variants"].add(model_variant)
            continue

        target["results_by_variant"][model_variant] = _result_from_row(
            row=row,
            result_id=int(result_id),
        )

    return list(grouped.values())


def _result_from_row(
    *,
    row: dict[str, Any],
    result_id: int,
) -> dict[str, Any]:
    return {
        "sentiment_index_result_id": result_id,
        "artifact_id": int(row["artifact_id"]),
        "supply_demand_association_score": row[
            "supply_demand_association_score"
        ],
        "recognized_feature_count": int(row["recognized_feature_count"]),
        "unique_token_count": int(row["unique_token_count"]),
        "vocabulary_coverage": float(row["vocabulary_coverage"]),
        "inference_status": str(row["inference_status"]),
    }


def _build_history_signals(
    *,
    history_rows: list[dict[str, Any]],
    calibration: SignalCalibration,
) -> dict[int, list[DailyCommentSignal]]:
    """과거 추론 결과를 같은 calibration으로 신호로 변환해 묶는다."""
    grouped_targets = _group_latest_document_targets(history_rows)
    history: dict[int, list[DailyCommentSignal]] = defaultdict(list)

    for target in grouped_targets:
        # 과거 이력은 비교용 참고값이므로 판정할 수 없는 날은 건너뛴다.
        if target["duplicate_variants"]:
            continue

        signal = _build_signal(target=target, calibration=calibration)

        if signal is None:
            continue

        history[target["stock_id"]].append(signal)

    return dict(history)


def _build_signal(
    *,
    target: dict[str, Any],
    calibration: SignalCalibration,
) -> DailyCommentSignal | None:
    """대상 한 건의 댓글 수급 신호를 계산한다."""
    results_by_variant = target["results_by_variant"]

    if set(results_by_variant.keys()) != {"positive", "negative"}:
        return None

    return build_daily_comment_signal(
        stock_id=target["stock_id"],
        stock_code=target["stock_code"],
        stock_name=target["stock_name"],
        model_date=target["model_date"],
        daily_document_id=target["daily_document_id"],
        comment_count=target["comment_count"],
        actual_supply_index=target["actual_supply_index"],
        supply_data_status=target["supply_data_status"],
        supply_observed_at=target["supply_observed_at"],
        results_by_variant=results_by_variant,
        calibration=calibration,
    )


def _process_target(
    *,
    target: dict[str, Any],
    calibration: SignalCalibration,
    previous_signals: list[DailyCommentSignal],
    provider: str,
    model: str,
    get_client: Callable[[], LlmReportClient],
    select_existing_hashes: Callable[..., list[dict[str, Any]]],
    insert_report: Callable[..., int],
    update_report: Callable[..., bool],
) -> str:
    request: ReportGenerationRequest | None = None
    input_hash: str | None = None
    existing_report: dict[str, Any] | None = None
    is_supply_update = False
    try:
        if target["duplicate_variants"]:
            raise ValueError(
                "방향별 추론 결과가 둘 이상 존재합니다: "
                f"variants={sorted(target['duplicate_variants'])}"
            )

        daily_signal = _build_signal(target=target, calibration=calibration)

        if daily_signal is None:
            return "not_ready"

        history = build_comment_signal_history(
            current_signal=daily_signal,
            previous_signals=previous_signals,
        )
        request = _build_generation_request(
            target=target,
            daily_signal=daily_signal,
            history=history,
            calibration=calibration,
            provider=provider,
            model=model,
        )
        input_hash = calculate_report_input_hash(request)
        existing_reports = select_existing_hashes(
            positive_result_ids=[request.positive_result_id],
            negative_result_ids=[request.negative_result_id],
            provider=provider,
            model=model,
            prompt_version=request.prompt_version,
            report_schema_version=request.report_schema_version,
            evidence_schema_version=request.evidence_schema_version,
        )
        existing_hashes = {row["input_hash"] for row in existing_reports}
        existing_report = existing_reports[0] if existing_reports else None
        supply_transition = _resolve_supply_transition(
            existing_report=existing_report,
            request=request,
        )
        if supply_transition == "keep":
            return "existing"
        is_supply_update = supply_transition == "update"

        if input_hash in existing_hashes and not is_supply_update:
            return "existing"

        if existing_hashes and not is_supply_update:
            is_supply_update = True
            logger.info("입력 해시 변경으로 인한 보고서 갱신: daily_document_id=%s, stock_code=%s", target.get("daily_document_id"), target.get("stock_code"))

        if not should_request_llm_commentary(request):
            report_record = _build_report_record(
                request=request,
                input_hash=input_hash,
                status="insufficient_evidence",
                generation_result=None,
            )
            if is_supply_update:
                if not update_report(
                    llm_report_id=int(existing_report["llm_report_id"]),
                    report_record=report_record,
                ):
                    raise RuntimeError("v13 수급 상태 보고서 갱신에 실패했습니다.")
                return "updated"
            insert_report(report_record=report_record)
            return "deterministic"

        generation_result = get_client().generate_report(
            request,
            on_rejection=partial(_log_rejected_commentary, request=request),
        )
        report_record = _build_report_record(
            request=request,
            input_hash=input_hash,
            status="ready",
            generation_result=generation_result,
        )
        if is_supply_update:
            if not update_report(
                llm_report_id=int(existing_report["llm_report_id"]),
                report_record=report_record,
            ):
                raise RuntimeError("v13 수급 상태 보고서 갱신에 실패했습니다.")
            return "updated"
        insert_report(report_record=report_record)
        return "generated"
    except LlmReportResponseError as error:
        # 각 시도의 원문은 on_rejection이 이미 기록했다. 여기서는 최종
        # 실패만 남겨 시도 기록과 결과를 이어 볼 수 있게 한다.
        logger.warning(
            "LLM 보고서 최종 실패(검증 2회 거부): stock_code=%s, "
            "stock_name=%s, model_date=%s, 사유=%s",
            target.get("stock_code"),
            target.get("stock_name"),
            target.get("model_date"),
            error.rejection_reason,
        )
        if request is None or input_hash is None:
            return "failed"
        fallback_record = _build_report_record(
            request=request,
            input_hash=input_hash,
            status="insufficient_evidence",
            generation_result=None,
        )
        if is_supply_update:
            if update_report(
                llm_report_id=int(existing_report["llm_report_id"]),
                report_record=fallback_record,
            ):
                return "updated"
            return "failed"
        insert_report(report_record=fallback_record)
        return "deterministic"
    except Exception as error:
        logger.exception(
            "LLM 보고서 생성 실패: daily_document_id=%s, "
            "stock_code=%s, model_date=%s, error_type=%s",
            target.get("daily_document_id"),
            target.get("stock_code"),
            target.get("model_date"),
            type(error).__name__,
        )
        return "failed"


def _resolve_supply_transition(
    *,
    existing_report: dict[str, Any] | None,
    request: ReportGenerationRequest,
) -> str:
    """기존 v13과 신규 수급 관측의 허용된 상태 전이만 판정한다."""
    if existing_report is None:
        return "none"

    existing_status = existing_report.get("supply_data_status")
    requested_status = request.supply_data_status
    if existing_status not in {"estimated", "confirmed"}:
        raise ValueError("기존 v13 보고서의 수급 상태가 올바르지 않습니다.")

    if existing_status == "confirmed" and requested_status == "estimated":
        return "keep"
    if existing_status == "estimated" and requested_status == "confirmed":
        return "update"
    if existing_status != "estimated" or requested_status != "estimated":
        return "none"

    existing_observed_at = existing_report.get("supply_observed_at")
    requested_observed_at = request.supply_observed_at
    if not isinstance(existing_observed_at, datetime) or not isinstance(
        requested_observed_at,
        datetime,
    ):
        raise ValueError(
            "estimated v13 갱신 판정에는 수급 관측 시각이 필요합니다."
        )
    if requested_observed_at > existing_observed_at:
        return "update"
    return "keep"


def _log_rejected_commentary(
    *,
    request: ReportGenerationRequest,
    attempt: int,
    commentary: LlmMarketCommentary | None,
    reason: str,
) -> None:
    """
    검증에서 걸러진 응답 본문을 시도 단위로 입력 신호와 함께 남긴다.

    거부 사유만으로는 검증 규칙이 실제로 필요했는지 판단할 수 없다.
    어떤 문장이 어떤 입력값에서 걸렸는지 함께 봐야 규칙이 과했는지
    확인할 수 있으므로 원문과 정형 근거를 같이 기록한다.

    재시도로 최종 성공한 경우에도 앞선 시도의 기록은 남는다. 규제가
    쓸모 있는 보고서를 막았는지 판단하려면 걸러진 문장 자체가 필요하기
    때문이다.
    """
    evidence = request.evidence
    logger.warning(
        "LLM 응답 검증 거부: stock_code=%s, stock_name=%s, model_date=%s, "
        "daily_document_id=%s, 시도=%s, supply_direction=%s, "
        "actual_supply_index=%s, recognized_feature_count=%s, "
        "comment_signal_score=%s, previous_signal_score=%s, "
        "signal_change=%s, signal_ma5=%s, 사유=%s\n"
        "  [market_commentary] %s\n"
        "  [conclusion] %s",
        request.stock_code,
        request.stock_name,
        request.model_date,
        request.daily_document_id,
        attempt,
        evidence.supply_direction,
        evidence.actual_supply_index,
        request.recognized_feature_count,
        evidence.comment_signal_score,
        evidence.previous_signal_score,
        evidence.signal_change,
        evidence.signal_ma5,
        reason,
        "(본문 없음)" if commentary is None else commentary.market_commentary,
        "(본문 없음)" if commentary is None else commentary.conclusion,
    )


def _build_generation_request(
    *,
    target: dict[str, Any],
    daily_signal: DailyCommentSignal,
    history: CommentSignalHistory,
    calibration: SignalCalibration,
    provider: str,
    model: str,
) -> ReportGenerationRequest:
    results_by_variant = target["results_by_variant"]
    return ReportGenerationRequest(
        daily_document_id=daily_signal.daily_document_id,
        positive_result_id=results_by_variant["positive"][
            "sentiment_index_result_id"
        ],
        negative_result_id=results_by_variant["negative"][
            "sentiment_index_result_id"
        ],
        stock_id=daily_signal.stock_id,
        stock_code=daily_signal.stock_code,
        stock_name=daily_signal.stock_name,
        model_date=daily_signal.model_date,
        comment_count=daily_signal.comment_count,
        supply_state=classify_supply_state(daily_signal.actual_supply_index),
        active_model_variant=daily_signal.active_model_variant,
        predicted_score=daily_signal.predicted_score,
        recognized_feature_count=daily_signal.recognized_feature_count,
        unique_token_count=daily_signal.unique_token_count,
        vocabulary_coverage=daily_signal.vocabulary_coverage,
        inference_status=daily_signal.inference_status,
        supply_data_status=daily_signal.supply_data_status,
        supply_observed_at=daily_signal.supply_observed_at,
        evidence=build_signal_evidence(
            daily_signal=daily_signal,
            history=history,
        ),
        model_name=calibration.model_name,
        model_version=calibration.model_version,
        artifact_schema_version=calibration.artifact_schema_version,
        calibration_schema_version=(
            calibration.calibration_schema_version
        ),
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        report_schema_version=REPORT_SCHEMA_VERSION,
        evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
    )


def _build_report_record(
    *,
    request: ReportGenerationRequest,
    input_hash: str,
    status: str,
    generation_result: ReportGenerationResult | None,
) -> dict[str, Any]:
    return {
        "stock_id": request.stock_id,
        "model_date": request.model_date,
        "daily_document_id": request.daily_document_id,
        "positive_result_id": request.positive_result_id,
        "negative_result_id": request.negative_result_id,
        "provider": request.provider,
        "model": request.model,
        "prompt_version": request.prompt_version,
        "report_schema_version": request.report_schema_version,
        "evidence_schema_version": request.evidence_schema_version,
        "status": status,
        "report_json": build_report_json(
            request=request,
            status=status,
            generation_result=generation_result,
        ),
        "input_hash": input_hash,
        "provider_response_id": (
            None
            if generation_result is None
            else generation_result.provider_response_id
        ),
        "input_tokens": (
            None if generation_result is None else generation_result.input_tokens
        ),
        "output_tokens": (
            None if generation_result is None else generation_result.output_tokens
        ),
        "supply_data_status": request.supply_data_status,
        "supply_observed_at": request.supply_observed_at,
    }


def _validate_summary(summary: dict[str, int]) -> None:
    state_total = sum(
        summary[key] for key in SUMMARY_KEYS if key != "input_count"
    )
    if state_total != summary["input_count"]:
        raise AssertionError(
            "LLM 보고서 실행 요약 합계가 input_count와 다릅니다."
        )


def configure_logging(log_dir: Path = LOG_DIR) -> Path:
    """
    실행 진입점에서만 로그 핸들러를 구성한다.

    모듈은 `logging.getLogger(__name__)`으로 기록만 하고 핸들러를 붙이지
    않는다. 상위 실행기가 이 job을 import해서 호출하면 상위 설정이
    그대로 적용된다.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (
        f"generate_llm_reports_{date.today().isoformat()}.log"
    )
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    return log_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="지정 기간의 미생성 LLM 보고서를 생성해 DB에 저장합니다."
    )
    parser.add_argument("--start-date", required=True, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="종료일 YYYY-MM-DD")
    parser.add_argument(
        "--calibration-path",
        type=Path,
        default=None,
        help="사용할 calibration artifact 경로",
    )
    arguments = parser.parse_args()
    log_path = configure_logging()
    logger.info("실행 로그 경로: %s", log_path)

    try:
        start_date = date.fromisoformat(arguments.start_date)
        end_date = date.fromisoformat(arguments.end_date)
    except ValueError as error:
        parser.error(f"날짜 형식이 잘못됐습니다: {error}")
        return

    summary = run_pending_llm_report_generation(
        report_start_date=start_date,
        report_end_date=end_date,
        calibration_path=arguments.calibration_path,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
