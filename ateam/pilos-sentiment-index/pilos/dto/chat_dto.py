"""챗봇 요청·응답과 공개 출처의 전달 계약을 정의한다."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

ChatAction = Literal[
    "stock_analysis",
    "stock_metric",
    "service_knowledge",
]

ChatMetric = Literal[
    "supply_demand_index",
    "individual_buy_volume",
    "individual_sell_volume",
]

CHAT_ACTIONS = frozenset({
    "stock_analysis",
    "stock_metric",
    "service_knowledge",
})

CHAT_METRICS = frozenset({
    "supply_demand_index",
    "individual_buy_volume",
    "individual_sell_volume",
})


ChatRoute = Literal[
    "general",
    "stock_metric",
    "stock_analysis",
    "service_knowledge",
    "restricted",
]

ChatStatus = Literal[
    "ready",
    "needs_clarification",
    "not_ready",
    "not_found",
    "unavailable",
    "failed",
]

ChatSourceType = Literal[
    "mysql_metric",
    "llm_report",
    "service_document",
]


@dataclass(frozen=True, slots=True)
class ChatRequestDTO:
    """Flask에서 ChatbotService로 전달할 사용자 요청이다."""
    message: str = ""
    block_key: str | None = None
    action: ChatAction | None = None
    metric: ChatMetric | None = None
    session_id: str | None = None
    stock_code: str | None = None
    model_date: date | None = None


@dataclass(frozen=True, slots=True)
class ChatSourceDTO:
    """사용자에게 공개할 수 있는 답변 근거다."""

    type: ChatSourceType
    label: str
    version: str | None = None
    stock_code: str | None = None
    model_date: date | None = None


@dataclass(frozen=True, slots=True)
class ChatResponseDTO:
    """ChatbotService가 Flask에 반환할 공개 응답이다."""

    status: ChatStatus
    answer: str
    route: ChatRoute
    session_id: str | None = None
    stock_code: str | None = None
    as_of: date | None = None
    sources: tuple[ChatSourceDTO, ...] = ()
    warnings: tuple[str, ...] = ()
