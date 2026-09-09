import argparse
import json

from typing import Any

from pilos.analysis.single_comment_inference import (
    DEFAULT_TOP_N,
    analyze_single_comment,
)
from pilos.analysis.tokenizer import create_current_kiwi
from pilos.dto.single_comment_inference_dto import (
    SingleCommentAnalysisDTO,
    single_comment_analysis_to_dict,
)
from pilos.jobs.predict_model import (
    load_registered_model_artifacts,
)
from pilos.model_config import ACTIVE_SERVICE_MODEL_VERSION, SERVICE_MODEL_VARIANTS


# CLI:
# uv run python -m pilos.jobs.analyze_single_comment \
#   --text "오늘 더 떨어지면 추가 매수한다"
#
# 이 job은 DB에 결과를 저장하지 않는다. 사용자가 모델 반응을 확인하는
# 체험 기능이며 일별 댓글 수급 신호와 계약을 공유하지 않는다.

def run_single_comment_analysis(
    *,
    comment_text: str,
    top_n: int = DEFAULT_TOP_N,
    load_artifacts: Any = load_registered_model_artifacts,
    tokenizer: Any | None = None,
) -> SingleCommentAnalysisDTO:
    """등록된 두 방향 모델로 단일 댓글을 분석한다."""
    artifacts_by_variant = {}

    for model_variant in SERVICE_MODEL_VARIANTS:
        _artifact_record, model_artifacts = load_artifacts(
            model_variant=model_variant,
            model_version=ACTIVE_SERVICE_MODEL_VERSION,
        )
        artifacts_by_variant[model_variant] = model_artifacts

    missing_variants = {"positive", "negative"} - artifacts_by_variant.keys()

    if missing_variants:
        raise ValueError(
            f"등록된 모델 아티팩트가 없습니다: {sorted(missing_variants)}"
        )

    if tokenizer is None:
        tokenizer = create_current_kiwi()

    return analyze_single_comment(
        comment_text=comment_text,
        tokenizer=tokenizer,
        positive_model_artifacts=artifacts_by_variant["positive"],
        negative_model_artifacts=artifacts_by_variant["negative"],
        top_n=top_n,
    )


def build_single_comment_response(
    analysis: SingleCommentAnalysisDTO,
) -> dict[str, Any]:
    """기존 CLI 호출자를 공통 단일 댓글 응답 계약에 연결한다."""
    return single_comment_analysis_to_dict(analysis)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="입력한 댓글 한 건을 두 Ridge 모델로 분석합니다."
    )
    parser.add_argument("--text", required=True, help="분석할 댓글 원문")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    arguments = parser.parse_args()
    analysis = run_single_comment_analysis(
        comment_text=arguments.text,
        top_n=arguments.top_n,
    )
    print(
        json.dumps(
            build_single_comment_response(analysis),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
