import math

from datetime import date
from typing import Any, Mapping, Sequence

import numpy as np

from pilos.dto.comment_signal_dto import (
    CommentSignalHistory,
    DailyCommentSignal,
    ModelVariant,
    SignalCalibration,
    SignalStatus,
    SupplyDirection,
    VariantCalibration,
)


SIGNAL_CALIBRATION_SCHEMA_VERSION = 1

# 0~100 백분위를 1단위로 보관한다. 재추론 표본이 수천 건 규모이므로
# 1% 간격이면 화면에 표시할 정수 점수를 안정적으로 복원할 수 있다.
QUANTILE_LEVELS: tuple[float, ...] = tuple(
    float(level) for level in range(0, 101)
)
MODEL_VARIANTS: tuple[ModelVariant, ...] = ("positive", "negative")

# 당일을 제외한 직전 거래일 신호 평균에 사용할 최대 표본 수다.
SIGNAL_MOVING_AVERAGE_WINDOW = 5

# 화면과 deterministic 요약이 함께 사용할 상대 강도 구간이다.
# 방향은 supply_direction이 담당하므로 여기에 긍정·부정 표현을 쓰지 않는다.
SIGNAL_LEVEL_BANDS: tuple[tuple[int, int, str], ...] = (
    (0, 19, "매우 낮음"),
    (20, 39, "낮음"),
    (40, 59, "보통"),
    (60, 79, "높음"),
    (80, 100, "매우 높음"),
)

SIGNAL_MEANING_NOTICE = (
    "댓글 수급 신호는 온라인 투자자 댓글의 언어 패턴과 실제 개인투자자 "
    "수급 사이에서 학습된 관계를 기반으로, 현재 댓글에 대한 모델 반응이 "
    "과거 동일 수급 방향 대비 어느 정도 수준인지 0~100으로 수치화한 "
    "값입니다. 감성 확률이나 미래 수급·주가 예측값이 아닙니다."
)

_SUPPLY_DIRECTION_BY_VARIANT: dict[ModelVariant, SupplyDirection] = {
    "positive": "BUY",
    "negative": "SELL",
}


def _finite_float(value: Any, field_name: str) -> float:
    """Decimal을 포함한 DB 수치를 유한한 float으로 변환한다."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.")

    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name}는 유한한 숫자여야 합니다."
        ) from error

    if not math.isfinite(converted):
        raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.")

    return converted


def resolve_supply_direction(
    actual_supply_index: Any,
) -> SupplyDirection:
    """
    실제 개인투자자 수급지수의 부호로 수급 방향을 결정한다.

    수급지수가 0이거나 None이면 방향 없음을 명시한다.
    """
    if actual_supply_index is None:
        return "NEUTRAL"
    index = _finite_float(actual_supply_index, "actual_supply_index")

    if index > 0:
        return "BUY"
    if index < 0:
        return "SELL"
    return "NEUTRAL"


def resolve_model_variant(
    supply_direction: SupplyDirection,
) -> ModelVariant | None:
    """수급 방향에 대응하는 Ridge variant를 반환한다."""
    for model_variant, direction in _SUPPLY_DIRECTION_BY_VARIANT.items():
        if direction == supply_direction:
            return model_variant

    return None


def resolve_signal_level(comment_signal_score: int) -> str:
    """0~100 신호 점수를 화면용 상대 강도 문구로 변환한다."""
    if (
        isinstance(comment_signal_score, bool)
        or not isinstance(comment_signal_score, int)
    ):
        raise ValueError("신호 점수는 정수여야 합니다.")

    for lower_bound, upper_bound, label in SIGNAL_LEVEL_BANDS:
        if lower_bound <= comment_signal_score <= upper_bound:
            return label

    raise ValueError("신호 점수는 0 이상 100 이하여야 합니다.")


def build_variant_calibration(
    *,
    model_variant: ModelVariant,
    artifact_id: int,
    predicted_scores: Sequence[Any],
) -> VariantCalibration:
    """
    한 방향의 재추론 predicted_score 분포에서 백분위 기준을 만든다.

    입력:
    - predicted_scores: 해당 방향 모델이 학습 범위를 재추론한 원본
      점수 목록이다. 임의로 만든 값을 넣지 않는다.

    출력:
    - 0~100 백분위에 대응하는 실제 점수 배열을 가진 calibration이다.
    """
    if model_variant not in MODEL_VARIANTS:
        raise ValueError(
            "model_variant는 positive 또는 negative여야 합니다."
        )

    if (
        not isinstance(artifact_id, int)
        or isinstance(artifact_id, bool)
        or artifact_id <= 0
    ):
        raise ValueError("artifact_id는 1 이상의 정수여야 합니다.")

    if isinstance(predicted_scores, (str, bytes)):
        raise ValueError("predicted_scores는 숫자 목록이어야 합니다.")

    scores = np.asarray(
        [
            _finite_float(score, "predicted_score")
            for score in predicted_scores
        ],
        dtype=float,
    )

    # 분포를 표현할 수 없는 표본으로 백분위를 만들면 화면에 정상 신호처럼
    # 보이는 잘못된 값이 생기므로 최소 표본 수를 요구한다.
    if scores.size < len(QUANTILE_LEVELS):
        raise ValueError(
            "calibration 표본이 백분위 구간 수보다 적습니다: "
            f"variant={model_variant}, count={scores.size}"
        )

    quantile_scores = np.quantile(
        scores,
        np.asarray(QUANTILE_LEVELS, dtype=float) / 100.0,
        method="linear",
    )

    # np.quantile은 비내림차순을 보장하지만 부동소수점 오차로 아주 작은
    # 역전이 생기면 백분위 역산이 단조성을 잃으므로 명시적으로 고정한다.
    quantile_scores = np.maximum.accumulate(quantile_scores)

    if not np.isfinite(quantile_scores).all():
        raise ValueError("calibration 백분위 값에 유한하지 않은 값이 있습니다.")

    return VariantCalibration(
        model_variant=model_variant,
        artifact_id=artifact_id,
        sample_count=int(scores.size),
        quantile_levels=QUANTILE_LEVELS,
        quantile_scores=tuple(float(value) for value in quantile_scores),
    )


def calculate_score_percentile(
    *,
    calibration: VariantCalibration,
    predicted_score: Any,
) -> float:
    """
    raw predicted_score가 과거 분포에서 차지하는 백분위를 계산한다.

    분포 최솟값보다 작으면 0, 최댓값보다 크면 100으로 안전하게 clamp한다.
    """
    score = _finite_float(predicted_score, "predicted_score")
    quantile_scores = np.asarray(calibration.quantile_scores, dtype=float)
    quantile_levels = np.asarray(calibration.quantile_levels, dtype=float)

    # np.interp는 xp 범위를 벗어난 입력을 양 끝 값으로 고정하므로
    # 분포 밖 입력이 자동으로 0 또는 100으로 clamp된다.
    percentile = float(
        np.interp(score, quantile_scores, quantile_levels)
    )
    return min(100.0, max(0.0, percentile))


def calculate_comment_signal_score(
    *,
    calibration: VariantCalibration,
    predicted_score: Any,
) -> int:
    """
    방향별 규칙에 따라 raw 점수를 0~100 댓글 수급 신호로 변환한다.

    positive 모델은 raw 점수가 클수록 해당 수급 방향의 모델 반응이 강한
    것으로 처리한다. negative 모델은 더 강한 음수가 강한 반응이므로
    백분위 방향을 뒤집는다.

    반환값 50은 감성 중립이 아니라 과거 동일 모델 출력 분포의 중간
    수준이라는 뜻이다.
    """
    percentile = calculate_score_percentile(
        calibration=calibration,
        predicted_score=predicted_score,
    )

    if calibration.model_variant == "negative":
        percentile = 100.0 - percentile

    # 단조성을 유지하는 반올림을 사용한다.
    signal_score = math.floor(percentile + 0.5)
    return min(100, max(0, signal_score))


def build_daily_comment_signal(
    *,
    stock_id: int,
    stock_code: str,
    stock_name: str,
    model_date: date,
    daily_document_id: int,
    comment_count: int,
    actual_supply_index: Any,
    results_by_variant: Mapping[str, Mapping[str, Any]],
    calibration: SignalCalibration,
    supply_data_status: str = "confirmed",
    supply_observed_at: Any = None,
) -> DailyCommentSignal:
    """
    일별문서 한 건의 댓글 수급 신호를 계산한다.

    입력:
    - results_by_variant: positive와 negative 각각의 저장된 추론 결과다.
      `supply_demand_association_score`, `recognized_feature_count`,
      `artifact_id`, `sentiment_index_result_id`를 사용한다.
    - calibration: 해당 모델 버전과 연결이 검증된 calibration이다.

    출력:
    - 방향, 활성 모델, raw 점수와 0~100 신호를 담은 DTO다.

    예외 처리:
    - 실제 수급지수가 0이면 방향을 임의로 고르지 않고 `no_direction`으로
      처리하며 신호 점수를 계산하지 않는다.
    - 추론 가능 여부는 DB에 저장된 `inference_status`만으로 판단하며,
      `recognized_feature_count`를 이용해 상태를 다시 판정하지 않는다.
    """
    supply_direction = resolve_supply_direction(actual_supply_index)
    model_variant = resolve_model_variant(supply_direction)
    common = {
        "stock_id": int(stock_id),
        "stock_code": str(stock_code).zfill(6),
        "stock_name": str(stock_name),
        "model_date": model_date,
        "daily_document_id": int(daily_document_id),
        "comment_count": int(comment_count),
        "actual_supply_index": (
            _finite_float(actual_supply_index, "actual_supply_index")
            if actual_supply_index is not None
            else 0.0
        ),
        "supply_data_status": supply_data_status or "confirmed",
        "supply_observed_at": supply_observed_at,
        "supply_direction": supply_direction,
        "model_name": calibration.model_name,
        "model_version": calibration.model_version,
        "artifact_schema_version": calibration.artifact_schema_version,
        "calibration_schema_version": (
            calibration.calibration_schema_version
        ),
    }

    if model_variant is None:
        return DailyCommentSignal(
            active_model_variant=None,
            active_result_id=None,
            active_artifact_id=None,
            predicted_score=None,
            recognized_feature_count=None,
            inference_status=None,
            unique_token_count=None,
            vocabulary_coverage=None,
            comment_signal_score=None,
            signal_level=None,
            signal_status="no_direction",
            **common,
        )

    active_result = results_by_variant.get(model_variant)

    if active_result is None:
        raise ValueError(
            "활성 수급 방향의 추론 결과가 없습니다: "
            f"variant={model_variant}, "
            f"daily_document_id={daily_document_id}"
        )

    variant_calibration = calibration.variant(model_variant)
    active_artifact_id = int(active_result["artifact_id"])

    if active_artifact_id != variant_calibration.artifact_id:
        raise ValueError(
            "추론 결과의 artifact_id와 calibration artifact_id가 다릅니다: "
            f"variant={model_variant}, "
            f"result={active_artifact_id}, "
            f"calibration={variant_calibration.artifact_id}"
        )

    predicted_score = _finite_float(
        active_result["supply_demand_association_score"],
        "supply_demand_association_score",
    )
    recognized_feature_count = int(
        active_result["recognized_feature_count"]
    )

    if recognized_feature_count < 0:
        raise ValueError("recognized_feature_count는 0 이상이어야 합니다.")

    inference_status = str(active_result["inference_status"])
    unique_token_count = int(active_result["unique_token_count"])
    vocabulary_coverage = _finite_float(
        active_result["vocabulary_coverage"],
        "vocabulary_coverage",
    )

    if inference_status not in {"ready", "insufficient_features"}:
        raise ValueError("지원하지 않는 inference_status입니다.")

    quality = {
        "inference_status": inference_status,
        "unique_token_count": unique_token_count,
        "vocabulary_coverage": vocabulary_coverage,
    }

    if inference_status == "insufficient_features":
        return DailyCommentSignal(
            active_model_variant=model_variant,
            active_result_id=_optional_int(
                active_result.get("sentiment_index_result_id")
            ),
            active_artifact_id=active_artifact_id,
            predicted_score=predicted_score,
            recognized_feature_count=recognized_feature_count,
            comment_signal_score=None,
            signal_level=None,
            signal_status="insufficient_features",
            **quality,
            **common,
        )

    comment_signal_score = calculate_comment_signal_score(
        calibration=variant_calibration,
        predicted_score=predicted_score,
    )
    return DailyCommentSignal(
        active_model_variant=model_variant,
        active_result_id=_optional_int(
            active_result.get("sentiment_index_result_id")
        ),
        active_artifact_id=active_artifact_id,
        predicted_score=predicted_score,
        recognized_feature_count=recognized_feature_count,
        comment_signal_score=comment_signal_score,
        signal_level=resolve_signal_level(comment_signal_score),
        signal_status="ready",
        **quality,
        **common,
    )


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def build_comment_signal_history(
    *,
    current_signal: DailyCommentSignal,
    previous_signals: Sequence[DailyCommentSignal],
) -> CommentSignalHistory:
    """
    당일 신호와 비교할 직전 거래일 값과 이동평균을 만든다.

    입력:
    - previous_signals: 당일보다 앞선 거래일의 신호 목록이다. 순서와
      무관하게 model_date 기준으로 다시 정렬한다.

    출력:
    - 직전 `ready` 신호, 당일과의 차이, 당일을 제외한 최근 최대
      5거래일 평균을 담은 DTO다.

    신호가 계산되지 않은 날(`no_direction`, `insufficient_features`)은
    평균과 직전 값 계산에서 제외한다. 없는 값을 만들어 채우지 않는다.
    """
    ready_signals = sorted(
        (
            signal
            for signal in previous_signals
            if signal.signal_status == "ready"
            and signal.comment_signal_score is not None
            and signal.model_date < current_signal.model_date
        ),
        key=lambda signal: signal.model_date,
        reverse=True,
    )

    if not ready_signals:
        return CommentSignalHistory(
            previous_signal_score=None,
            signal_change=None,
            signal_ma5=None,
            history_size=0,
        )

    window = ready_signals[:SIGNAL_MOVING_AVERAGE_WINDOW]
    previous_signal_score = int(ready_signals[0].comment_signal_score)
    average = sum(
        int(signal.comment_signal_score) for signal in window
    ) / len(window)
    signal_ma5 = math.floor(average + 0.5)
    signal_change = (
        None
        if current_signal.comment_signal_score is None
        else int(current_signal.comment_signal_score)
        - previous_signal_score
    )
    return CommentSignalHistory(
        previous_signal_score=previous_signal_score,
        signal_change=signal_change,
        signal_ma5=signal_ma5,
        history_size=len(window),
    )


def verify_calibration_matches_artifact(
    *,
    calibration: SignalCalibration,
    artifact_record: Mapping[str, Any],
) -> None:
    """
    calibration이 현재 추론에 사용하는 artifact와 같은 모델인지 검증한다.

    비교 대상은 `artifacts` 테이블에 실제로 존재하는 컬럼이다. 모델명,
    버전, artifact 종류·스키마, 토크나이저, vectorizer, scaler와 학습
    Dataset 기간 중 하나라도 다르면 다른 모델의 분포를 사용하게 되므로
    차단한다.
    """
    model_variant = artifact_record["model_variant"]
    variant_calibration = calibration.variant(model_variant)
    comparable_fields = (
        ("model_name", calibration.model_name),
        ("model_version", calibration.model_version),
        ("artifact_type", calibration.artifact_type),
        (
            "artifact_schema_version",
            calibration.artifact_schema_version,
        ),
        ("tokenizer_version", calibration.tokenizer_version),
        ("vectorizer_name", calibration.vectorizer_name),
        ("scaler_name", calibration.scaler_name),
    )

    for field_name, calibration_value in comparable_fields:
        artifact_value = artifact_record[field_name]

        if artifact_value != calibration_value:
            raise ValueError(
                "calibration과 모델 artifact 정보가 다릅니다: "
                f"field={field_name}, artifact={artifact_value}, "
                f"calibration={calibration_value}"
            )

    dataset_fields = (
        ("dataset_start_date", calibration.dataset_start_date),
        ("dataset_end_date", calibration.dataset_end_date),
    )

    # artifacts 행은 date, calibration JSON은 문자열이므로 표기를 맞춘다.
    for field_name, calibration_value in dataset_fields:
        artifact_value = artifact_record[field_name]
        normalized = (
            artifact_value.isoformat()
            if isinstance(artifact_value, date)
            else str(artifact_value)
        )

        if normalized != calibration_value:
            raise ValueError(
                "calibration과 모델 artifact 정보가 다릅니다: "
                f"field={field_name}, artifact={normalized}, "
                f"calibration={calibration_value}"
            )

    artifact_id = int(artifact_record["artifact_id"])

    if artifact_id != variant_calibration.artifact_id:
        raise ValueError(
            "calibration과 모델 artifact_id가 다릅니다: "
            f"variant={model_variant}, artifact={artifact_id}, "
            f"calibration={variant_calibration.artifact_id}"
        )


__all__ = [
    "MODEL_VARIANTS",
    "QUANTILE_LEVELS",
    "SIGNAL_CALIBRATION_SCHEMA_VERSION",
    "SIGNAL_LEVEL_BANDS",
    "SIGNAL_MEANING_NOTICE",
    "SIGNAL_MOVING_AVERAGE_WINDOW",
    "SignalStatus",
    "build_comment_signal_history",
    "build_daily_comment_signal",
    "build_variant_calibration",
    "calculate_comment_signal_score",
    "calculate_score_percentile",
    "resolve_model_variant",
    "resolve_signal_level",
    "resolve_supply_direction",
    "verify_calibration_matches_artifact",
]
