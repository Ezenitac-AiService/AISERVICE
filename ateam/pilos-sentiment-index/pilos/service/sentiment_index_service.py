from dataclasses import replace

from pilos.dto.sentiment_index_dto import SentimentIndexDTO
from pilos.service.active_model_service import (
    ActiveServiceModelError,
    get_active_service_model_context,
)
from pilos.storage.sentiment_index_storage import (
    read_latest_sentiment_indexes,
    read_sentiment_indexes_by_stock_code,
    SentimentIndexStorageError,
)
class SentimentIndexServiceError(RuntimeError):
    pass


def _analysis_status(item: SentimentIndexDTO) -> str:
    """현재 수급 방향이 선택한 결과의 저장 품질 상태를 공개 상태로 만든다."""
    if item.model_date is None:
        return "not_found"
    if item.positive_model is None or item.negative_model is None:
        return "inference_pending"

    supply_index = item.actual_supply_demand_index
    if supply_index is None:
        return "inference_pending"
    if supply_index == 0:
        return "no_direction"

    active_model = (
        item.positive_model
        if supply_index > 0
        else item.negative_model
    )
    if active_model.inference_status is None:
        return "unknown"
    if active_model.inference_status == "insufficient_features":
        return "insufficient_features"
    if active_model.inference_status == "ready":
        return "ready"
    raise SentimentIndexServiceError("지원하지 않는 활성 추론 상태입니다.")


def _with_analysis_status(
    items: list[SentimentIndexDTO],
) -> list[SentimentIndexDTO]:
    return [replace(item, analysis_status=_analysis_status(item)) for item in items]

# 메인 화면에 모든 종목의 심리지수 전달
def get_main_sentiment_indexes() -> list[SentimentIndexDTO]:
    try:
        context = get_active_service_model_context()
        items = read_latest_sentiment_indexes(
            context.positive_artifact_id,
            context.negative_artifact_id,
        )
        return _with_analysis_status(items)
    except (ActiveServiceModelError, SentimentIndexStorageError) as err:
        raise SentimentIndexServiceError("데이터를 불러올 수 없음") from err

# 상세 화면에 선택한 종목의 심리지수 전달
def get_stock_detail_sentiment_indexes(stock_code: str) -> list[SentimentIndexDTO]:
    try:
        context = get_active_service_model_context()
        items = read_sentiment_indexes_by_stock_code(
            stock_code,
            context.positive_artifact_id,
            context.negative_artifact_id,
        )
        return _with_analysis_status(items)
    except (ActiveServiceModelError, SentimentIndexStorageError) as err:
        raise SentimentIndexServiceError("데이터를 불러올 수 없음") from err
