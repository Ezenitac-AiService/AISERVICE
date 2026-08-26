import json

from datetime import date

import numpy as np

from sqlalchemy import bindparam, text

from pilos.storage.db import get_engine


def _prepare_sentiment_index_result(
    inference_result: dict,
) -> dict:
    """
    모델 추론 결과를 sentiment_index_result INSERT 자료형으로 변환한다.

    입력:
    - inference_result: jobs 추론기가 생성한 일별문서 한 건의 결과다.

    출력:
    - 기존 결과 테이블 컬럼명과 JSON 문자열로 변환된 dict를 반환한다.

    선정된 v4 모델은 댓글 수를 특성으로 사용하지 않으므로
    comment_count_contribution은 수학적으로 기여가 없다는 뜻의 0.0으로
    기록한다. 키워드에는 LLM 보고서와 분석 검수에 사용할 rank, word,
    tfidf, coefficient, contribution을 모두 보존한다.
    """
    required_fields = {
        "daily_document_id",
        "artifact_id",
        "predicted_supply_demand_index",
        "intercept",
        "text_score",
        "recognized_feature_count",
        "unique_token_count",
        "vocabulary_coverage",
        "inference_status",
        "positive_keywords",
        "negative_keywords",
    }
    missing_fields = required_fields - inference_result.keys()

    if missing_fields:
        raise ValueError(
            "추론 결과에 DB 적재 필드가 없습니다: "
            f"{sorted(missing_fields)}"
        )

    daily_document_id = inference_result["daily_document_id"]
    artifact_id = inference_result["artifact_id"]
    recognized_feature_count = inference_result[
        "recognized_feature_count"
    ]
    unique_token_count = inference_result["unique_token_count"]
    vocabulary_coverage = inference_result["vocabulary_coverage"]
    inference_status = inference_result["inference_status"]

    for field_name, value in (
        ("daily_document_id", daily_document_id),
        ("artifact_id", artifact_id),
    ):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                f"{field_name}는 1 이상의 정수여야 합니다."
            )

    if (
        not isinstance(recognized_feature_count, int)
        or isinstance(recognized_feature_count, bool)
        or recognized_feature_count < 0
    ):
        raise ValueError(
            "recognized_feature_count는 0 이상의 정수여야 합니다."
        )

    if (
        not isinstance(unique_token_count, int)
        or isinstance(unique_token_count, bool)
        or unique_token_count < 0
    ):
        raise ValueError("unique_token_count must be a non-negative integer.")

    if (
        not isinstance(vocabulary_coverage, (int, float, np.integer, np.floating))
        or isinstance(vocabulary_coverage, (bool, np.bool_))
        or not np.isfinite(vocabulary_coverage)
        or not 0.0 <= vocabulary_coverage <= 1.0
    ):
        raise ValueError("vocabulary_coverage must be between zero and one.")

    if inference_status not in {"ready", "insufficient_features"}:
        raise ValueError("inference_status is not supported.")

    numeric_fields = (
        "predicted_supply_demand_index",
        "intercept",
        "text_score",
    )
    numeric_values = {}

    for field_name in numeric_fields:
        value = inference_result[field_name]

        if (
            not isinstance(value, (int, float, np.integer, np.floating))
            or isinstance(value, (bool, np.bool_))
            or not np.isfinite(value)
        ):
            raise ValueError(
                f"{field_name}는 유한한 숫자여야 합니다."
            )

        numeric_values[field_name] = float(value)

    serialized_keywords = {}

    for field_name in (
        "positive_keywords",
        "negative_keywords",
    ):
        keywords = inference_result[field_name]

        if not isinstance(keywords, list):
            raise ValueError(
                f"{field_name}는 list여야 합니다."
            )

        for keyword in keywords:
            if not isinstance(keyword, dict):
                raise ValueError(
                    f"{field_name}의 각 항목은 dict여야 합니다."
                )

            required_keyword_fields = {
                "rank",
                "word",
                "tfidf",
                "coefficient",
                "contribution",
            }
            missing_keyword_fields = (
                required_keyword_fields - keyword.keys()
            )

            if missing_keyword_fields:
                raise ValueError(
                    f"{field_name} 항목에 필드가 없습니다: "
                    f"{sorted(missing_keyword_fields)}"
                )

        try:
            serialized_keywords[field_name] = json.dumps(
                keywords,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{field_name}를 JSON으로 변환할 수 없습니다."
            ) from error

    return {
        "daily_document_id": daily_document_id,
        "artifact_id": artifact_id,
        "supply_demand_association_score": numeric_values[
            "predicted_supply_demand_index"
        ],
        "intercept": numeric_values["intercept"],
        "text_score": numeric_values["text_score"],
        "comment_count_contribution": 0.0,
        "recognized_feature_count": recognized_feature_count,
        "unique_token_count": unique_token_count,
        "vocabulary_coverage": float(vocabulary_coverage),
        "inference_status": inference_status,
        "positive_contribution_keywords": serialized_keywords[
            "positive_keywords"
        ],
        "negative_contribution_keywords": serialized_keywords[
            "negative_keywords"
        ],
    }


def select_daily_documents_for_inference(
    *,
    tokenizer_version: str,
    inference_start_date: date,
    inference_end_date: date,
    artifact_ids: tuple[int, ...],
) -> list[dict]:
    """
    지정 기간에서 수급 데이터가 존재하는 최신 일별문서만 조회한다.

    입력:
    - tokenizer_version: 최종 모델 bundle과 동일해야 하는 토큰 버전이다.
    - inference_start_date, inference_end_date: 양 끝 날짜를 포함하는
      추론 대상 기간이다.

    출력:
    - 종목·날짜별 최신 daily_document 중 같은 stock_id와 model_date에
      대응하는 supply_demand 행이 존재하는 문서 목록을 반환한다.

    supply_demand_index 자체는 모델 입력으로 선택하지 않는다. 현재
    text-only 모델은 댓글 문서만 사용하며, INNER JOIN은 해당 종목의
    실제 거래일 수급 데이터 존재 여부를 서비스 eligibility 조건으로
    적용하기 위한 것이다. 따라서 휴장일 문서는 추론 대상에서 제외된다.
    """
    tokenizer_version = tokenizer_version.strip()

    if not tokenizer_version:
        raise ValueError(
            "tokenizer_version은 비어 있을 수 없습니다."
        )

    if inference_start_date > inference_end_date:
        raise ValueError(
            "추론 시작일은 종료일보다 늦을 수 없습니다."
        )

    if not artifact_ids or any(
        not isinstance(artifact_id, int) or artifact_id <= 0
        for artifact_id in artifact_ids
    ):
        raise ValueError("active artifact ids are invalid.")

    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError("active artifact ids are duplicated.")

    sql = text("""
        SELECT
            dd.daily_document_id,
            s.stock_code,
            dd.model_date,
            dd.tfidf_text,
            dd.comment_count
        FROM daily_document AS dd
        INNER JOIN stock AS s
            ON s.stock_id = dd.stock_id
        LEFT JOIN supply_demand AS sd
            ON sd.stock_id = dd.stock_id
           AND sd.trade_date = dd.model_date
        WHERE dd.tokenizer_version = :tokenizer_version
          AND dd.model_date >= :inference_start_date
          AND dd.model_date <= :inference_end_date
          AND (
              SELECT COUNT(DISTINCT sir.artifact_id)
              FROM sentiment_index_result AS sir
              WHERE sir.daily_document_id = dd.daily_document_id
                AND sir.artifact_id IN :artifact_ids
          ) < :required_artifact_count
          AND NOT EXISTS (
              SELECT 1
              FROM daily_document AS newer_dd
              WHERE newer_dd.stock_id = dd.stock_id
                AND newer_dd.model_date = dd.model_date
                AND newer_dd.tokenizer_version
                    = dd.tokenizer_version
                AND newer_dd.daily_document_id
                    > dd.daily_document_id
          )
        ORDER BY
            dd.model_date ASC,
            dd.stock_id ASC
    """).bindparams(bindparam("artifact_ids", expanding=True))

    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            sql,
            {
                "tokenizer_version": tokenizer_version,
                "inference_start_date": inference_start_date,
                "inference_end_date": inference_end_date,
                "artifact_ids": artifact_ids,
                "required_artifact_count": len(artifact_ids),
            },
        )

        return [
            dict(row)
            for row in result.mappings()
        ]


def insert_sentiment_index_results(
    *,
    inference_results: list[dict],
) -> dict[str, int]:
    """
    신규 모델 추론 결과만 sentiment_index_result에 일괄 적재한다.

    입력:
    - inference_results: 한 모델 또는 여러 모델이 생성한 일별문서 추론
      결과 목록이다. 각 결과에는 daily_document_id와 artifact_id가 있어야
      한다.

    출력:
    - input_count, inserted_count, existing_count를 담은 dict를 반환한다.
      빈 목록이면 DB에 연결하지 않고 모두 0을 반환한다.

    기존 (daily_document_id, artifact_id) 결과는 이력으로 보존하고
    UPDATE나 Upsert로 덮어쓰지 않는다. 신규 결과들은 한 트랜잭션에서
    INSERT하며 하나라도 실패하면 전체 신규 INSERT를 롤백한다.
    """
    if not isinstance(inference_results, list):
        raise ValueError(
            "inference_results는 list여야 합니다."
        )

    if not inference_results:
        return {
            "input_count": 0,
            "inserted_count": 0,
            "existing_count": 0,
        }

    prepared_results = [
        _prepare_sentiment_index_result(result)
        for result in inference_results
    ]
    result_keys = [
        (
            result["daily_document_id"],
            result["artifact_id"],
        )
        for result in prepared_results
    ]

    if len(result_keys) != len(set(result_keys)):
        raise ValueError(
            "입력에 같은 daily_document_id와 artifact_id가 중복되었습니다."
        )

    daily_document_ids = sorted({
        result["daily_document_id"]
        for result in prepared_results
    })
    artifact_ids = sorted({
        result["artifact_id"]
        for result in prepared_results
    })
    select_existing_sql = text("""
        SELECT
            daily_document_id,
            artifact_id
        FROM sentiment_index_result
        WHERE daily_document_id IN :daily_document_ids
          AND artifact_id IN :artifact_ids
    """).bindparams(
        bindparam(
            "daily_document_ids",
            expanding=True,
        ),
        bindparam(
            "artifact_ids",
            expanding=True,
        ),
    )
    insert_sql = text("""
        INSERT INTO sentiment_index_result (
            daily_document_id,
            artifact_id,
            supply_demand_association_score,
            intercept,
            text_score,
            comment_count_contribution,
            recognized_feature_count,
            unique_token_count,
            vocabulary_coverage,
            inference_status,
            positive_contribution_keywords,
            negative_contribution_keywords
        ) VALUES (
            :daily_document_id,
            :artifact_id,
            :supply_demand_association_score,
            :intercept,
            :text_score,
            :comment_count_contribution,
            :recognized_feature_count,
            :unique_token_count,
            :vocabulary_coverage,
            :inference_status,
            :positive_contribution_keywords,
            :negative_contribution_keywords
        )
    """)
    engine = get_engine()

    with engine.begin() as conn:
        existing_rows = list(conn.execute(
            select_existing_sql,
            {
                "daily_document_ids": daily_document_ids,
                "artifact_ids": artifact_ids,
            },
        ).mappings())
        existing_keys = {
            (
                int(row["daily_document_id"]),
                int(row["artifact_id"]),
            )
            for row in existing_rows
        }
        pending_results = [
            result
            for result in prepared_results
            if (
                result["daily_document_id"],
                result["artifact_id"],
            ) not in existing_keys
        ]

        if pending_results:
            conn.execute(
                insert_sql,
                pending_results,
            )

    inserted_count = len(pending_results)

    return {
        "input_count": len(prepared_results),
        "inserted_count": inserted_count,
        "existing_count": (
            len(prepared_results) - inserted_count
        ),
    }
