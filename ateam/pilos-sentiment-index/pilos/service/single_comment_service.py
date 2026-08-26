from typing import Any

from pilos.analysis.single_comment_inference import (
    DEFAULT_TOP_N,
    analyze_single_comment,
)
from pilos.dto.single_comment_inference_dto import (
    SingleCommentAnalysisDTO,
)
from pilos.service.active_model_service import (
    ActiveServiceModelError,
    ActiveServiceModelContext,
    get_active_service_model_context,
    get_active_service_tokenizer,
)


class SingleCommentInputError(ValueError):
    """사용자 입력으로 단일 댓글 분석을 수행할 수 없는 상태."""


class SingleCommentServiceError(RuntimeError):
    """모델 조회·로딩 또는 분석 사용 사례 조합 실패."""


def get_single_comment_analysis(
    comment_text: str,
    *,
    top_n: int = DEFAULT_TOP_N,
    context_loader: Any = get_active_service_model_context,
    tokenizer_loader: Any = get_active_service_tokenizer,
    tokenizer: Any | None = None,
) -> SingleCommentAnalysisDTO:
    """등록된 서비스 모델 두 개로 단일 댓글 분석 요청을 조합한다."""
    if not isinstance(comment_text, str) or not comment_text.strip():
        raise SingleCommentInputError(
            "comment_text는 비어 있지 않은 문자열이어야 합니다."
        )

    try:
        context: ActiveServiceModelContext = context_loader()
        if tokenizer is None:
            tokenizer = tokenizer_loader(context)
    except ActiveServiceModelError as exc:
        raise SingleCommentServiceError(
            "단일 댓글 분석 모델을 준비할 수 없습니다."
        ) from exc
    except Exception as exc:
        raise SingleCommentServiceError(
            "단일 댓글 분석 모델을 준비할 수 없습니다."
        ) from exc

    try:
        return analyze_single_comment(
            comment_text=comment_text,
            tokenizer=tokenizer,
            positive_model_artifacts=context.positive_model_artifacts,
            negative_model_artifacts=context.negative_model_artifacts,
            top_n=top_n,
        )
    except ValueError as exc:
        raise SingleCommentInputError(str(exc)) from exc
    except Exception as exc:
        raise SingleCommentServiceError(
            "단일 댓글 분석을 수행할 수 없습니다."
        ) from exc
