from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal


SupplyDirection = Literal["BUY", "SELL", "NEUTRAL"]
ModelVariant = Literal["positive", "negative"]
SignalStatus = Literal[
    "ready",
    "insufficient_features",
    "no_direction",
]


@dataclass(frozen=True, slots=True)
class VariantCalibration:
    """
    한 방향 Ridge 모델의 과거 출력 분포를 표현하는 calibration이다.

    quantile_levels와 quantile_scores는 같은 길이이며 index가 서로
    대응한다. quantile_levels는 0~100의 백분위 지점이고
    quantile_scores는 해당 지점의 실제 predicted_score다.

    이 값은 모델 artifact 성격의 데이터이며 운영 DB에 적재하지 않는다.
    """

    model_variant: ModelVariant
    artifact_id: int
    sample_count: int
    quantile_levels: tuple[float, ...]
    quantile_scores: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SignalCalibration:
    """
    특정 Ridge 모델 버전과 연결된 방향별 calibration 묶음이다.

    모델 identity 필드는 calibration을 만든 재추론이 실제로 어떤
    artifact를 사용했는지 확인하기 위한 값이다. 추론 시점의 artifact와
    하나라도 다르면 signal 계산을 진행하지 않는다.
    """

    calibration_schema_version: int
    generated_at: str
    source_scope: str
    source_row_count: int
    model_name: str
    model_version: int
    artifact_type: str
    artifact_schema_version: int
    tokenizer_version: str
    vectorizer_name: str
    scaler_name: str
    dataset_start_date: str
    dataset_end_date: str
    variants: tuple[VariantCalibration, ...]

    def variant(
        self,
        model_variant: ModelVariant,
    ) -> VariantCalibration:
        """지정한 방향의 calibration을 반환한다."""
        for calibration in self.variants:
            if calibration.model_variant == model_variant:
                return calibration

        raise KeyError(
            f"calibration에 {model_variant} 방향이 없습니다."
        )


@dataclass(frozen=True, slots=True)
class DailyCommentSignal:
    """
    일별문서 한 건의 댓글 수급 신호 계산 결과다.

    `comment_signal_score`는 감성 확률이나 미래 예측값이 아니다. 현재
    실제 개인투자자 수급 방향 안에서 댓글에 대한 모델 반응이 과거 동일
    방향 사례 대비 어느 정도 수준인지를 0~100으로 표현한 상대값이다.

    `signal_status`가 `ready`가 아니면 `comment_signal_score`와
    `signal_level`은 None이다.
    """

    stock_id: int
    stock_code: str
    stock_name: str
    model_date: date
    daily_document_id: int
    comment_count: int
    actual_supply_index: float
    supply_direction: SupplyDirection
    active_model_variant: ModelVariant | None
    active_result_id: int | None
    active_artifact_id: int | None
    predicted_score: float | None
    recognized_feature_count: int | None
    comment_signal_score: int | None
    signal_level: str | None
    signal_status: SignalStatus
    model_name: str
    model_version: int
    artifact_schema_version: int
    calibration_schema_version: int
    inference_status: str | None = None
    unique_token_count: int | None = None
    vocabulary_coverage: float | None = None
    supply_data_status: str = "confirmed"
    supply_observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CommentSignalHistory:
    """
    직전 거래일과 최근 거래일 평균을 담은 비교용 정형 값이다.

    `signal_ma5`는 당일을 제외한 직전 최대 5거래일의 `ready` 신호
    평균이다. 당일 값을 포함하지 않으므로 당일 신호와 비교하는 기준선으로
    사용할 수 있다. 비교 가능한 과거 신호가 없으면 모든 값이 None이다.
    """

    previous_signal_score: int | None
    signal_change: int | None
    signal_ma5: int | None
    history_size: int
