from dataclasses import asdict, dataclass
from typing import Any, Literal

from pilos.dto.keyword_contribution_dto import (
    KeywordContributionDTO,
)


ModelVariant = Literal["positive", "negative"]

SINGLE_COMMENT_NOTICE = (
    "이 결과는 입력한 댓글 한 건에 대한 모델 반응입니다. 모델은 일별 "
    "댓글 집합 단위로 학습됐으므로 이 값을 일별 댓글 수급 신호나 "
    "0~100 점수로 해석하지 않습니다."
)


@dataclass(frozen=True, slots=True)
class SingleCommentInferenceDTO:
    """단일 댓글의 모델 분석 결과를 전달한다."""

    comment_text: str
    processed_text: str
    text_score: float
    recognized_feature_count: int
    positive_keywords: tuple[
        KeywordContributionDTO,
        ...,
    ]
    negative_keywords: tuple[
        KeywordContributionDTO,
        ...,
    ]


@dataclass(frozen=True, slots=True)
class SingleCommentAnalysisDTO:
    """
    단일 댓글을 Positive·Negative 두 모델로 분석한 결과를 전달한다.

    이 결과는 사용자가 모델 반응을 체험하는 기능을 위한 것이며 일별
    분석과 계약을 공유하지 않는다. Ridge는 일별 댓글 집합(document)
    단위로 학습되었으므로 단일 댓글 결과에 일별 `comment_signal_score`
    calibration을 적용하지 않는다.

    각 방향 결과는 `SingleCommentInferenceDTO` 계약을 그대로 따른다.
    따라서 모델 절편과 전체 수급지수 예측값을 단일 댓글 결과인 것처럼
    합산하지 않고 인식된 단어 기여도의 합인 `text_score`만 제공한다.
    """

    comment_text: str
    processed_text: str
    token_count: int
    positive: SingleCommentInferenceDTO
    negative: SingleCommentInferenceDTO

    def result_for(
        self,
        model_variant: ModelVariant,
    ) -> SingleCommentInferenceDTO:
        """지정한 방향 모델의 분석 결과를 반환한다."""
        if model_variant == "positive":
            return self.positive
        if model_variant == "negative":
            return self.negative

        raise ValueError(
            "model_variant는 positive 또는 negative여야 합니다."
        )


def single_comment_analysis_to_dict(
    analysis: SingleCommentAnalysisDTO,
) -> dict[str, Any]:
    """두 방향 단일 댓글 분석을 공통 API·CLI 전달 구조로 바꾼다."""
    return {
        "comment_text": analysis.comment_text,
        "processed_text": analysis.processed_text,
        "token_count": analysis.token_count,
        "positive_model": _variant_payload(analysis.positive),
        "negative_model": _variant_payload(analysis.negative),
        "notice": SINGLE_COMMENT_NOTICE,
    }


def _variant_payload(
    result: SingleCommentInferenceDTO,
) -> dict[str, Any]:
    return {
        "text_score": result.text_score,
        "recognized_feature_count": result.recognized_feature_count,
        "positive_keywords": [
            asdict(keyword) for keyword in result.positive_keywords
        ],
        "negative_keywords": [
            asdict(keyword) for keyword in result.negative_keywords
        ],
    }
