import json

from datetime import date, timedelta
from typing import Any

from sqlalchemy import bindparam, text

from pilos.storage.db import get_engine


# 직전 거래일과 이동평균 비교에 사용할 조회 창이다. 휴장일이 섞여도
# 최근 5거래일을 확보할 수 있도록 달력 기준으로 넉넉히 조회한 뒤
# analysis에서 실제 거래일만 사용한다.
SIGNAL_HISTORY_LOOKBACK_DAYS = 21


def select_latest_llm_report_targets(
    *,
    report_start_date: date,
    report_end_date: date,
    model_name: str,
    model_version: int,
    artifact_schema_version: int,
) -> list[dict[str, Any]]:
    """
    기간 내 최신 일별문서와 LLM 보고서 생성에 필요한 주변 행을 조회한다.

    일별 보고서는 더 이상 기여 키워드와 댓글 원문을 사용하지 않으므로
    `positive_contribution_keywords`와 `negative_contribution_keywords`는
    조회하지 않는다. 두 컬럼은 추론 검수와 단일 댓글 기능을 위해 DB에
    그대로 보존한다.

    실제 DB 연결은 호출자가 이 함수를 사용할 때만 발생한다. jobs 단위
    테스트에서는 이 함수를 mock으로 대체해 DB 없이 상태 판정을 검증한다.
    """
    if report_start_date > report_end_date:
        raise ValueError("보고서 시작일은 종료일보다 늦을 수 없습니다.")

    sql = text("""
        SELECT
            dd.daily_document_id,
            dd.stock_id,
            s.stock_code,
            s.stock_name,
            dd.model_date,
            dd.comment_count,
            sir.sentiment_index_result_id,
            sir.artifact_id,
            a.model_variant,
            sir.supply_demand_association_score,
            sir.intercept,
            sir.text_score,
            sir.recognized_feature_count,
            sir.unique_token_count,
            sir.vocabulary_coverage,
            sir.inference_status,
            sd.supply_demand_index AS actual_supply_index,
            sd.data_status AS supply_data_status,
            sd.observed_at AS supply_observed_at
        FROM daily_document AS dd
        INNER JOIN stock AS s
            ON s.stock_id = dd.stock_id
        LEFT JOIN supply_demand AS sd
            ON sd.stock_id = dd.stock_id
           AND sd.trade_date = dd.model_date
        LEFT JOIN sentiment_index_result AS sir
            ON sir.daily_document_id = dd.daily_document_id
        LEFT JOIN artifacts AS a
            ON a.artifact_id = sir.artifact_id
           AND a.model_name = :model_name
           AND a.model_version = :model_version
           AND a.artifact_schema_version = :artifact_schema_version
        WHERE dd.model_date >= :report_start_date
          AND dd.model_date <= :report_end_date
          AND NOT EXISTS (
              SELECT 1
              FROM daily_document AS newer_dd
              WHERE newer_dd.stock_id = dd.stock_id
                AND newer_dd.model_date = dd.model_date
                AND newer_dd.daily_document_id > dd.daily_document_id
          )
        ORDER BY
            dd.model_date ASC,
            dd.stock_id ASC,
            dd.daily_document_id ASC,
            a.model_variant ASC,
            sir.sentiment_index_result_id ASC
    """)
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "report_start_date": report_start_date,
                "report_end_date": report_end_date,
                "model_name": model_name,
                "model_version": model_version,
                "artifact_schema_version": artifact_schema_version,
            },
        ).mappings()

        return [dict(row) for row in rows]


def select_signal_history_results(
    *,
    stock_ids: list[int],
    history_start_date: date,
    history_end_date: date,
    model_name: str,
    model_version: int,
    artifact_schema_version: int,
) -> list[dict[str, Any]]:
    """
    직전 거래일 비교에 필요한 과거 추론 결과를 종목별로 조회한다.

    신규 테이블을 만들지 않고 기존 `sentiment_index_result`의 저장된
    raw 점수를 그대로 사용한다. 백분위 변환은 analysis가 담당한다.
    """
    if not stock_ids:
        return []

    if history_start_date > history_end_date:
        raise ValueError("이력 시작일은 종료일보다 늦을 수 없습니다.")

    sql = text("""
        SELECT
            dd.daily_document_id,
            dd.stock_id,
            s.stock_code,
            s.stock_name,
            dd.model_date,
            dd.comment_count,
            sir.sentiment_index_result_id,
            sir.artifact_id,
            a.model_variant,
            sir.supply_demand_association_score,
            sir.recognized_feature_count,
            sir.unique_token_count,
            sir.vocabulary_coverage,
            sir.inference_status,
            sd.supply_demand_index AS actual_supply_index,
            sd.data_status AS supply_data_status,
            sd.observed_at AS supply_observed_at
        FROM daily_document AS dd
        INNER JOIN stock AS s
            ON s.stock_id = dd.stock_id
        LEFT JOIN supply_demand AS sd
            ON sd.stock_id = dd.stock_id
           AND sd.trade_date = dd.model_date
        INNER JOIN sentiment_index_result AS sir
            ON sir.daily_document_id = dd.daily_document_id
        INNER JOIN artifacts AS a
            ON a.artifact_id = sir.artifact_id
           AND a.model_name = :model_name
           AND a.model_version = :model_version
           AND a.artifact_schema_version = :artifact_schema_version
        WHERE dd.stock_id IN :stock_ids
          AND dd.model_date >= :history_start_date
          AND dd.model_date <= :history_end_date
          AND NOT EXISTS (
              SELECT 1
              FROM daily_document AS newer_dd
              WHERE newer_dd.stock_id = dd.stock_id
                AND newer_dd.model_date = dd.model_date
                AND newer_dd.daily_document_id > dd.daily_document_id
          )
        ORDER BY
            dd.stock_id ASC,
            dd.model_date ASC,
            a.model_variant ASC
    """).bindparams(bindparam("stock_ids", expanding=True))
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "stock_ids": stock_ids,
                "history_start_date": history_start_date,
                "history_end_date": history_end_date,
                "model_name": model_name,
                "model_version": model_version,
                "artifact_schema_version": artifact_schema_version,
            },
        ).mappings()

        return [dict(row) for row in rows]


def resolve_history_start_date(report_start_date: date) -> date:
    """보고서 시작일 기준으로 이력 조회를 시작할 날짜를 계산한다."""
    return report_start_date - timedelta(days=SIGNAL_HISTORY_LOOKBACK_DAYS)


def select_llm_report_existing_hashes(
    *,
    positive_result_ids: list[int],
    negative_result_ids: list[int],
    provider: str,
    model: str,
    prompt_version: str,
    report_schema_version: int,
    evidence_schema_version: int,
) -> list[dict[str, Any]]:
    """같은 생성 고유키의 기존 보고서 hash만 조회한다."""
    if not positive_result_ids or not negative_result_ids:
        return []

    sql = text("""
        SELECT
            llm_report_id,
            positive_result_id,
            negative_result_id,
            input_hash,
            supply_data_status,
            supply_observed_at
        FROM llm_report
        WHERE positive_result_id IN :positive_result_ids
          AND negative_result_id IN :negative_result_ids
          AND provider = :provider
          AND model = :model
          AND prompt_version = :prompt_version
          AND report_schema_version = :report_schema_version
          AND evidence_schema_version = :evidence_schema_version
    """).bindparams(
        bindparam("positive_result_ids", expanding=True),
        bindparam("negative_result_ids", expanding=True),
    )
    engine = get_engine()

    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                sql,
                {
                    "positive_result_ids": positive_result_ids,
                    "negative_result_ids": negative_result_ids,
                    "provider": provider,
                    "model": model,
                    "prompt_version": prompt_version,
                    "report_schema_version": report_schema_version,
                    "evidence_schema_version": evidence_schema_version,
                },
            ).mappings()
        ]


def insert_llm_report(
    *,
    report_record: dict[str, Any],
) -> int:
    """검증된 LLM 보고서를 UPDATE 없이 신규 INSERT하고 report id를 반환한다."""
    required_fields = {
        "stock_id",
        "model_date",
        "daily_document_id",
        "positive_result_id",
        "negative_result_id",
        "provider",
        "model",
        "prompt_version",
        "report_schema_version",
        "evidence_schema_version",
        "status",
        "report_json",
        "input_hash",
        "provider_response_id",
        "input_tokens",
        "output_tokens",
        "supply_data_status",
        "supply_observed_at",
    }
    missing = required_fields - report_record.keys()

    if missing:
        raise ValueError(f"LLM 보고서 저장 필드가 없습니다: {sorted(missing)}")

    prepared = dict(report_record)
    prepared["report_json"] = json.dumps(
        prepared["report_json"],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    sql = text("""
        INSERT INTO llm_report (
            stock_id,
            model_date,
            daily_document_id,
            positive_result_id,
            negative_result_id,
            provider,
            model,
            prompt_version,
            report_schema_version,
            evidence_schema_version,
            status,
            report_json,
            input_hash,
            provider_response_id,
            input_tokens,
            output_tokens,
            supply_data_status,
            supply_observed_at
        ) VALUES (
            :stock_id,
            :model_date,
            :daily_document_id,
            :positive_result_id,
            :negative_result_id,
            :provider,
            :model,
            :prompt_version,
            :report_schema_version,
            :evidence_schema_version,
            :status,
            :report_json,
            :input_hash,
            :provider_response_id,
            :input_tokens,
            :output_tokens,
            :supply_data_status,
            :supply_observed_at
        )
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            report_json = VALUES(report_json),
            input_hash = VALUES(input_hash),
            provider_response_id = VALUES(provider_response_id),
            input_tokens = VALUES(input_tokens),
            output_tokens = VALUES(output_tokens),
            supply_data_status = VALUES(supply_data_status),
            supply_observed_at = VALUES(supply_observed_at)
    """)
    engine = get_engine()

    with engine.begin() as conn:
        result = conn.execute(sql, prepared)

    return int(result.lastrowid or 0)


def update_v13_llm_report_for_supply_change(
    *,
    llm_report_id: int,
    report_record: dict[str, Any],
) -> bool:
    """estimated v13 보고서를 confirmed 또는 더 최신 estimated로 갱신한다."""
    prepared = dict(report_record)
    prepared["llm_report_id"] = llm_report_id
    prepared["report_json"] = json.dumps(
        prepared["report_json"],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    sql = text("""
        UPDATE llm_report
        SET
            status = :status,
            report_json = :report_json,
            input_hash = :input_hash,
            provider_response_id = :provider_response_id,
            input_tokens = :input_tokens,
            output_tokens = :output_tokens,
            supply_data_status = :supply_data_status,
            supply_observed_at = :supply_observed_at,
            updated_at = CURRENT_TIMESTAMP
        WHERE llm_report_id = :llm_report_id
    """)
    engine = get_engine()

    with engine.begin() as conn:
        result = conn.execute(sql, prepared)

    return result.rowcount > 0
