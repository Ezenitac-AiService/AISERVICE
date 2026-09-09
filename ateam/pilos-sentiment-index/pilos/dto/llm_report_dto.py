import re

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


SupplyRegime = Literal["positive", "negative", "neutral"]
SupplyDirection = Literal["BUY", "SELL", "NEUTRAL"]
ModelVariant = Literal["positive", "negative"]
SignalStatus = Literal[
    "ready",
    "insufficient_features",
    "no_direction",
]

PROMPT_VERSION = "market_commentary_v13"
REPORT_SCHEMA_VERSION = 5

# 근거 계약 버전은 keyword evidence 전용 번호가 아니다. 근거의 종류가
# 키워드·대표 댓글에서 정형 수치로 바뀌었으므로 같은 버전 축을 계속
# 사용한다.
#
# v9~v11은 프롬프트 표현 계약과 응답 검증만 바꿨고 전달 필드와 저장
# 구조는 v8과 같으므로 report·evidence 스키마 버전은 올리지 않는다.
#
# llm_report 고유키에 prompt_version이 들어 있으므로, 프롬프트 계약이
# 바뀌면 prompt_version만 올려도 기존 행을 덮어쓰지 않고 새로 적재된다.
# 구조가 그대로인데 schema 버전을 올리면 소비자에게 잘못된 신호를 준다.
EVIDENCE_SCHEMA_VERSION = 3


# ---------------------------------------------------------------------------
# 조회 계약 (develop의 Flask 읽기 경로가 사용한다)
#
# 아래 두 정의는 develop 브랜치에서 먼저 만들어진 조회용 계약이다. 같은
# 파일 이름을 양쪽에서 각자 만든 탓에 병합 시 add/add 충돌이 나므로,
# 생성 계약과 조회 계약을 한 파일에 함께 둔다.
#
# 생성 계약(ReportGenerationRequest 등)은 보고서를 만들 때 쓰고,
# 조회 계약(LLMReportDTO)은 저장된 행을 읽어 Flask로 넘길 때 쓴다.
# 서로 방향이 다르므로 필드를 합치지 않는다.
# ---------------------------------------------------------------------------

LLMReportStatus = Literal["ready", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class LLMReportDTO:
    """`llm_report` 한 행을 그대로 옮긴 조회용 DTO다."""

    llm_report_id: int
    stock_id: int
    stock_code: str
    model_date: date
    daily_document_id: int
    comment_count: int

    positive_result_id: int
    negative_result_id: int

    provider: str
    model: str
    prompt_version: str
    report_schema_version: int
    evidence_schema_version: int

    status: LLMReportStatus
    report_json: dict[str, Any]
    input_hash: str

    provider_response_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    supply_data_status: str | None = None
    supply_observed_at: datetime | None = None
    current_supply_data_status: str | None = None
    current_supply_observed_at: datetime | None = None


def _contains_hangul(value: str) -> bool:
    """문자열에 한국어 음절 또는 자모가 하나 이상 있는지 확인한다."""
    return re.search(r"[가-힣ㄱ-ㅎㅏ-ㅣ]", value) is not None


class LlmMarketCommentary(BaseModel):
    """
    LLM이 작성하고 애플리케이션이 검증할 시장 코멘터리다.

    LLM은 분석기가 아니라 이미 계산된 정형 데이터를 자연어로 정리하는
    편집자이므로 응답 계약에 근거 목록이나 댓글 참조를 두지 않는다.
    """

    model_config = ConfigDict(extra="forbid")

    market_commentary: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=30, max_length=1200),
    ]
    conclusion: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=20, max_length=600),
    ]

    @field_validator("market_commentary", "conclusion")
    @classmethod
    def validate_korean_text(cls, value: str) -> str:
        """사용자용 본문이 실제 한국어를 포함하도록 검증한다."""
        if not _contains_hangul(value):
            raise ValueError("시장 코멘터리에는 한국어가 포함되어야 합니다.")
        return value


class LlmSupplyState(BaseModel):
    """실제 개인 수급지수로 코드가 결정한 화면용 수급 상태다."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    actual_supply_index: float
    active_regime: SupplyRegime
    supply_direction: SupplyDirection
    state_label: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    ]
    state_description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    ]


class LlmSignalEvidence(BaseModel):
    """
    LLM에 전달하는 정형 수치 근거다.

    모든 값은 코드와 모델이 이미 계산한 결과이며 LLM은 이 값들을 비교해
    요약만 한다. 키워드, 대표 댓글, 댓글 원문은 포함하지 않는다.

    `comment_signal_score`는 감성 확률이 아니라 같은 수급 방향의 과거
    모델 출력 분포 대비 상대 강도다. 50은 중립이 아니라 과거 분포의
    중간 수준을 뜻한다.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    actual_supply_index: float
    supply_direction: SupplyDirection
    signal_status: SignalStatus
    comment_signal_score: Annotated[int, Field(ge=0, le=100)] | None = None
    signal_level: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=20),
        ]
        | None
    ) = None
    comment_count: Annotated[int, Field(ge=0)]
    previous_signal_score: Annotated[int, Field(ge=0, le=100)] | None = None
    signal_change: Annotated[int, Field(ge=-100, le=100)] | None = None
    signal_ma5: Annotated[int, Field(ge=0, le=100)] | None = None

    @model_validator(mode="after")
    def validate_status_consistency(self) -> "LlmSignalEvidence":
        """신호 상태와 점수 존재 여부가 서로 어긋나지 않도록 검증한다."""
        if self.signal_status == "ready":
            if self.comment_signal_score is None or self.signal_level is None:
                raise ValueError(
                    "ready 상태에는 신호 점수와 강도 문구가 있어야 합니다."
                )
        elif (
            self.comment_signal_score is not None
            or self.signal_level is not None
        ):
            raise ValueError(
                "ready가 아닌 상태에는 신호 점수를 넣지 않습니다."
            )

        if self.signal_status == "no_direction" and (
            self.supply_direction != "NEUTRAL"
        ):
            raise ValueError(
                "no_direction 상태의 수급 방향은 NEUTRAL이어야 합니다."
            )

        if (
            self.signal_change is not None
            and self.previous_signal_score is not None
            and self.comment_signal_score is not None
            and self.signal_change
            != self.comment_signal_score - self.previous_signal_score
        ):
            raise ValueError(
                "signal_change는 현재 신호와 직전 신호의 차이여야 합니다."
            )

        if self.signal_change is not None and (
            self.previous_signal_score is None
        ):
            raise ValueError(
                "직전 신호가 없으면 signal_change를 만들지 않습니다."
            )

        return self

    def has_comparable_history(self) -> bool:
        """LLM 호출 가치가 있는 비교 값이 있는지 판정한다."""
        return (
            self.previous_signal_score is not None
            or self.signal_ma5 is not None
        )


class ReportGenerationRequest(BaseModel):
    """jobs가 만들고 LLM collection 어댑터가 소비할 보고서 요청이다."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    daily_document_id: Annotated[int, Field(ge=1)]
    positive_result_id: Annotated[int, Field(ge=1)]
    negative_result_id: Annotated[int, Field(ge=1)]
    stock_id: Annotated[int, Field(ge=1)]
    stock_code: Annotated[str, StringConstraints(pattern=r"^\d{6}$")]
    stock_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    ]
    model_date: date
    comment_count: Annotated[int, Field(ge=0)]
    supply_state: LlmSupplyState
    active_model_variant: ModelVariant | None = None
    predicted_score: float | None = None
    recognized_feature_count: Annotated[int, Field(ge=0)] | None = None
    unique_token_count: Annotated[int, Field(ge=0)] | None = None
    vocabulary_coverage: Annotated[float, Field(ge=0, le=1)] | None = None
    inference_status: Literal["ready", "insufficient_features"] | None = None
    supply_data_status: Literal["estimated", "confirmed"] = "confirmed"
    supply_observed_at: datetime | None = None
    evidence: LlmSignalEvidence
    model_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    ]
    model_version: Annotated[int, Field(ge=1)]
    artifact_schema_version: Annotated[int, Field(ge=1)]
    calibration_schema_version: Annotated[int, Field(ge=1)]
    provider: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    prompt_version: Literal["market_commentary_v13"] = PROMPT_VERSION
    report_schema_version: Literal[5] = REPORT_SCHEMA_VERSION
    evidence_schema_version: Literal[3] = EVIDENCE_SCHEMA_VERSION

    @model_validator(mode="after")
    def validate_signal_alignment(self) -> "ReportGenerationRequest":
        """수급 상태와 정형 근거가 같은 계산 결과를 가리키는지 검증한다."""
        if self.supply_state.supply_direction != (
            self.evidence.supply_direction
        ):
            raise ValueError(
                "수급 상태와 근거의 수급 방향이 다릅니다."
            )

        if self.supply_state.actual_supply_index != (
            self.evidence.actual_supply_index
        ):
            raise ValueError(
                "수급 상태와 근거의 수급지수가 다릅니다."
            )

        if self.comment_count != self.evidence.comment_count:
            raise ValueError("요청과 근거의 댓글 수가 다릅니다.")

        if self.evidence.signal_status == "no_direction" and (
            self.active_model_variant is not None
        ):
            raise ValueError(
                "방향이 없는 날에는 활성 모델을 지정하지 않습니다."
            )

        if self.evidence.signal_status != "no_direction" and (
            self.active_model_variant is None
        ):
            raise ValueError(
                "방향이 있는 날에는 활성 모델을 지정해야 합니다."
            )

        return self


class ReportGenerationResult(BaseModel):
    """공급자 SDK 형식을 제거한 검증 완료 보고서 생성 결과다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    commentary: LlmMarketCommentary
    provider_response_id: str | None = None
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None


@dataclass(frozen=True, slots=True)
class LlmCapabilityCheckResult:
    """공급자 SDK 객체를 제거한 capability 단일 점검 결과다."""

    check_name: str
    success: bool
    provider_response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    model_ids: tuple[str, ...] = ()
    error_type: str | None = None
    error_message: str | None = None
