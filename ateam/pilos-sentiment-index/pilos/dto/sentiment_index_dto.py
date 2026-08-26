from dataclasses import dataclass
from datetime import date, datetime
from pilos.dto.model_result_dto import ModelResultDTO

@dataclass(frozen=True, slots=True)
class SentimentIndexDTO:
    stock_code: str
    stock_name: str
    model_date: date | None
    comment_count: int | None
    actual_supply_demand_index: float | None
    actual_buy_volume: int | None
    actual_sell_volume: int | None
    supply_data_status: str | None
    supply_observed_at: datetime | None

    positive_model: ModelResultDTO | None
    negative_model: ModelResultDTO | None
    analysis_status: str | None
