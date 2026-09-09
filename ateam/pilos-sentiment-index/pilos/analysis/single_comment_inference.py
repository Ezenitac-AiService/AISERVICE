from typing import Any, Mapping

from pilos.analysis.modeling.model_inference import (
    analyze_text_contributions,
    split_text_only_ridge_coefficients,
)
from pilos.analysis.preprocessor import preprocess_comment_text
from pilos.analysis.tokenizer import tokenize_comment_for_current_model
from pilos.analysis.vectorizer import tokens_to_tfidf_text
from pilos.dto.keyword_contribution_dto import (
    KeywordContributionDTO,
)
from pilos.dto.single_comment_inference_dto import (
    SingleCommentAnalysisDTO,
    SingleCommentInferenceDTO,
)


DEFAULT_TOP_N = 10


def _to_contribution_dtos(
    keywords: list[dict[str, Any]],
) -> tuple[KeywordContributionDTO, ...]:
    """추론 키워드 dict를 웹 전달용 DTO로 변환한다."""
    return tuple(
        KeywordContributionDTO(
            keyword=str(keyword["word"]),
            contribution=float(keyword["contribution"]),
        )
        for keyword in keywords
    )


def analyze_single_comment_with_model(
    *,
    comment_text: str,
    processed_text: str,
    tfidf_text: str,
    model_artifacts: Mapping[str, Any],
    top_n: int = DEFAULT_TOP_N,
) -> SingleCommentInferenceDTO:
    """
    한 방향 모델로 단일 댓글의 특성 기여도를 계산한다.

    입력:
    - tfidf_text: 일별문서와 같은 규칙으로 만든 토큰 문자열이다.
    - model_artifacts: 검증을 통과한 text-only Ridge bundle이다.

    출력:
    - 인식된 단어 기여도의 합과 방향별 주요 키워드를 담은 DTO다.

    일별 추론과 같은 `analyze_text_contributions`를 사용하므로
    `TF-IDF × coefficient` 계산 규칙이 두 기능에서 동일하다.
    """
    vectorizer = model_artifacts["vectorizer"]
    ridge_model = model_artifacts["ridge_model"]
    feature_names = vectorizer.get_feature_names_out()
    text_coefficients, _intercept = split_text_only_ridge_coefficients(
        model=ridge_model,
        text_feature_count=len(feature_names),
    )
    tfidf_row = vectorizer.transform([tfidf_text])
    analysis = analyze_text_contributions(
        tfidf_row=tfidf_row,
        feature_names=feature_names,
        text_coefficients=text_coefficients,
        top_n=top_n,
    )
    return SingleCommentInferenceDTO(
        comment_text=comment_text,
        processed_text=processed_text,
        text_score=float(analysis["text_score"]),
        recognized_feature_count=int(analysis["recognized_feature_count"]),
        positive_keywords=_to_contribution_dtos(
            analysis["positive_keywords"]
        ),
        negative_keywords=_to_contribution_dtos(
            analysis["negative_keywords"]
        ),
    )


def analyze_single_comment(
    *,
    comment_text: str,
    tokenizer: Any,
    positive_model_artifacts: Mapping[str, Any],
    negative_model_artifacts: Mapping[str, Any],
    top_n: int = DEFAULT_TOP_N,
) -> SingleCommentAnalysisDTO:
    """
    사용자가 입력한 댓글 하나를 두 Ridge 모델로 분석한다.

    입력:
    - comment_text: 화면에서 입력받은 원문이다.
    - tokenizer: 학습과 같은 설정으로 만든 Kiwi 객체다.

    출력:
    - Positive와 Negative 모델의 반응을 각각 담은 DTO다.

    처리 순서는 기존 학습·추론 경로와 같다. 전처리 후 분석할 문자열이
    없으면 결과 대신 오류로 처리한다.

    이 함수는 일별 signal calibration을 사용하지 않는다. Ridge는 일별
    댓글 집합 단위로 학습됐으므로 단일 댓글 결과를 0~100 신호로 바꾸어
    보여주면 안 된다.
    """
    if not isinstance(comment_text, str) or not comment_text.strip():
        raise ValueError("분석할 댓글 원문이 비어 있습니다.")

    processed_text = preprocess_comment_text(comment_text)

    if not processed_text.strip():
        raise ValueError("전처리 후 분석할 문자열이 없습니다.")

    tokens = tokenize_comment_for_current_model(
        text=processed_text,
        tokenizer=tokenizer,
    )
    tfidf_text = tokens_to_tfidf_text(tokens)

    if not tfidf_text:
        raise ValueError("토큰화 후 분석할 특성이 없습니다.")

    return SingleCommentAnalysisDTO(
        comment_text=comment_text,
        processed_text=processed_text,
        token_count=len(tokens),
        positive=analyze_single_comment_with_model(
            comment_text=comment_text,
            processed_text=processed_text,
            tfidf_text=tfidf_text,
            model_artifacts=positive_model_artifacts,
            top_n=top_n,
        ),
        negative=analyze_single_comment_with_model(
            comment_text=comment_text,
            processed_text=processed_text,
            tfidf_text=tfidf_text,
            model_artifacts=negative_model_artifacts,
            top_n=top_n,
        ),
    )
