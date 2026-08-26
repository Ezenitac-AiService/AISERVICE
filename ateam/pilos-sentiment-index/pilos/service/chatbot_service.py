"""챗봇 질문 처리 결과를 공개 응답 DTO로 변환한다."""
import logging

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from pilos.dto.chat_dto import (
    ChatAction,
    ChatMetric,
    ChatRequestDTO,
    ChatResponseDTO,
    ChatRoute,
    ChatSourceDTO,
    ChatStatus,
)

from pilos.service.knowledge_cache import (
    get_cached_service_knowledge,
    is_cached_service_block,
)
from pilos.service.rag_service import (
    ServiceKnowledgeUnavailableError,
    generate_service_knowledge_answer,
)

from pilos.dto.supply_demand_dto import (
    ConfirmedSupplyDemand,
    SupplyDemandStorageError,
)

from pilos.storage.supply_demand_db import (
    select_confirmed_supply_demand,
    select_confirmed_supply_demand_ranking,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChatBlockDefinition:
    """클라이언트가 선택할 수 있는 공개 질문 블록의 서버 정본이다."""

    action: ChatAction
    message: str
    metric: ChatMetric | None = None
    needs_stock: bool = False


CHAT_BLOCK_DEFINITIONS: dict[str, ChatBlockDefinition] = {
    "stock_summary": ChatBlockDefinition(
        action="stock_analysis",
        message="선택한 날짜의 분석을 발표에서 설명할 수 있게 쉽게 요약해줘",
        needs_stock=True,
    ),
    "stock_supply_index": ChatBlockDefinition(
        action="stock_metric",
        metric="supply_demand_index",
        message="선택한 날짜의 실제 수급지수를 알려줘.",
        needs_stock=True,
    ),
    "stock_buy_volume": ChatBlockDefinition(
        action="stock_metric",
        metric="individual_buy_volume",
        message="선택한 날짜의 개인 매수량을 알려줘.",
        needs_stock=True,
    ),
    "stock_sell_volume": ChatBlockDefinition(
        action="stock_metric",
        metric="individual_sell_volume",
        message="선택한 날짜의 개인 매도량을 알려줘.",
        needs_stock=True,
    ),
    "service_overview": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS 서비스가 무엇을 연구하는지 핵심 목적만 짧게 설명해줘. "
            "세부 모델, 데이터 항목, 해석 유의사항은 제외하고 개요만 설명해줘."
        ),
    ),
    "service_research_target": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS의 연구 대상만 설명해줘. 어떤 댓글 데이터와 어떤 개인투자자 "
            "수급 데이터를 연결해서 무엇을 분석하는지에 집중해줘. 다른 모델 "
            "설명이나 데이터 항목 설명은 제외해줘."
        ),
    ),
    "service_models": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS의 Positive 모델과 Negative 모델이 각각 무엇을 의미하고 왜 두 "
            "방향으로 나누어 분석하는지 설명해줘. 두 모델 관련 내용에만 집중해줘."
        ),
    ),
    "service_interpretation": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS의 분석 결과를 사용자가 어떻게 읽어야 하는지 해석 방법만 쉽게 "
            "설명해줘. 투자 추천이나 미래 예측으로 오해하지 않도록 승인된 서비스 "
            "문서 내용에만 집중해줘."
        ),
    ),
    "service_columns": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS가 사용자에게 공개하는 주요 데이터 항목이 무엇인지 승인된 서비스 "
            "문서에 있는 내용만 짧게 설명해줘. 모든 항목은 한글 이름으로만 표현하고 "
            "영문 DB 컬럼명과 내부 구현용 필드는 제외해줘."
        ),
    ),
    "service_cautions": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS 분석 결과를 사용자가 해석할 때 주의해야 할 점만 설명해줘. 투자 "
            "추천이나 미래 수익 예측이 아니라는 점을 포함해 승인 문서에 있는 내용만 "
            "사용해줘."
        ),
    ),
    "service_positive_model": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS의 Positive 모델이 무엇인지 그 내용만 쉽게 설명해줘. Negative "
            "모델이나 데이터 항목 설명은 제외해줘."
        ),
    ),
    "service_negative_model": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS의 Negative 모델이 무엇인지 그 내용만 쉽게 설명해줘. Positive "
            "모델이나 데이터 항목 설명은 제외해줘."
        ),
    ),
    "service_model_difference": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS의 Positive 모델과 Negative 모델의 차이만 비교해서 쉽게 설명해줘. "
            "다른 서비스 기능이나 데이터 항목 설명은 제외해줘."
        ),
    ),
    "service_score_calculation": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS의 두 방향 모델 점수가 어떤 입력 요소를 바탕으로 계산되는지 승인된 "
            "서비스 문서 범위에서만 쉽게 설명해줘. 비공개 구현 세부정보는 제외해줘."
        ),
    ),
    "column_model_date": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS에서 분석 기준일이 무엇을 의미하는지 그 항목만 쉽게 설명해줘. "
            "영문 컬럼명은 표시하지 마."
        ),
    ),
    "column_text_score": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS에서 댓글 표현 점수가 무엇을 의미하는지 그 항목만 쉽게 설명해줘. "
            "미래 예측값이나 감성 확률로 오해하지 않도록 설명하고 영문 컬럼명은 "
            "표시하지 마."
        ),
    ),
    "column_comment_count": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS에서 분석 댓글 수가 무엇을 의미하고 분석에서 어떻게 사용되는지 "
            "그 항목만 쉽게 설명해줘. 영문 컬럼명은 표시하지 마."
        ),
    ),
    "column_supply_index": ChatBlockDefinition(
        action="service_knowledge",
        message=(
            "PILOS의 수급지수가 무엇을 의미하는지 승인된 서비스 문서에 정의된 "
            "범위에서만 쉽게 설명해줘. 정본에 없는 강도 구간이나 투자 판단 기준은 "
            "만들지 마."
        ),
    ),
    "column_buy_volume": ChatBlockDefinition(
        action="service_knowledge",
        message="PILOS에서 개인 매수량 데이터가 무엇을 의미하는지 그 항목만 쉽게 설명해줘.",
    ),
    "column_sell_volume": ChatBlockDefinition(
        action="service_knowledge",
        message="PILOS에서 개인 매도량 데이터가 무엇을 의미하는지 그 항목만 쉽게 설명해줘.",
    ),
}


def get_chat_block_definition(block_key: str) -> ChatBlockDefinition | None:
    """허용된 질문 키에 대응하는 서버 정의만 반환한다."""

    return CHAT_BLOCK_DEFINITIONS.get(block_key)

ServiceKnowledgeAnswer = Callable[
    [str],
    dict[str, Any],
]

StockAnalysisAnswer = Callable[
    [str, str, date],
    dict[str, Any],
]

ConfirmedSupplyDemandLookup = Callable[
    ...,
    ConfirmedSupplyDemand | None,
]

ConfirmedSupplyDemandRankingLookup = Callable[
    ...,
    list[ConfirmedSupplyDemand],
]


class StockAnalysisNotReadyError(RuntimeError):
    """선행 분석이나 보고서가 아직 준비되지 않은 상태."""


class StockAnalysisNotFoundError(RuntimeError):
    """요청한 종목과 날짜의 보고서가 없는 상태."""


class StockAnalysisServiceError(RuntimeError):
    """보고서 저장소 또는 연동에 실패한 상태."""


def _generate_stock_analysis_answer(
    message: str,
    stock_code: str,
    model_date: date,
) -> dict[str, Any]:
    """현재 v13 표시 보고서를 추가 LLM 호출 없이 챗봇 답변으로 만든다."""

    del message

    try:
        from pilos.service.llm_report_service import (
            LLMReportGenerationPendingError,
            LLMReportInferencePendingError,
            LLMReportNotFoundError,
            LLMReportServiceError,
            get_llm_report_for_display,
        )
    except ImportError as error:
        raise StockAnalysisServiceError(
            "LLM 보고서 계약을 불러올 수 없습니다."
        ) from error

    try:
        result = get_llm_report_for_display(
            stock_code,
            model_date,
        )
    except (
        LLMReportInferencePendingError,
        LLMReportGenerationPendingError,
    ) as error:
        raise StockAnalysisNotReadyError() from error
    except LLMReportNotFoundError as error:
        raise StockAnalysisNotFoundError() from error
    except LLMReportServiceError as error:
        raise StockAnalysisServiceError() from error

    result_stock_code = result.get("stock_code")
    result_model_date = result.get("model_date")

    if not isinstance(result_stock_code, str) or not result_stock_code.strip():
        raise StockAnalysisServiceError(
            "v13 보고서의 stock_code가 올바르지 않습니다."
        )

    if not isinstance(result_model_date, str):
        raise StockAnalysisServiceError(
            "v13 보고서의 model_date가 올바르지 않습니다."
        )

    try:
        parsed_model_date = date.fromisoformat(result_model_date)
    except ValueError as error:
        raise StockAnalysisServiceError(
            "v13 보고서의 model_date 형식이 올바르지 않습니다."
        ) from error

    answer_parts = []

    for field_name in (
        "market_commentary",
        "conclusion",
        "notice",
    ):
        field_value = result.get(field_name)
        if isinstance(field_value, str) and field_value.strip():
            answer_parts.append(field_value.strip())

    if not answer_parts:
        raise StockAnalysisServiceError(
            "v13 보고서의 공개 설명이 비어 있습니다."
        )

    return {
        "status": "ready",
        "answer": " ".join(answer_parts),
        "stock_code": result_stock_code.strip(),
        "model_date": parsed_model_date,
        "warnings": [],
    }


_SERVICE_KNOWLEDGE_STATUSES = {
    "ready",
    "not_found",
}

_PUBLIC_COLUMN_LABELS = {
    "actual_supply_demand_index": "실제 수급지수",
    "supply_demand_index": "실제 수급지수",
    "individual_buy_volume": "개인 매수량",
    "individual_sell_volume": "개인 매도량",
    "comment_count": "분석 댓글 수",
    "text_score": "댓글 표현 점수",
    "model_date": "분석 기준일",
}


def _localize_public_column_names(answer: str) -> str:
    """공개 설명에 포함된 내부 컬럼명을 사용자용 한글 명칭으로 바꾼다."""

    localized = answer
    for column_name, korean_label in _PUBLIC_COLUMN_LABELS.items():
        localized = localized.replace(column_name, korean_label)
    return localized


_INVESTMENT_RESTRICTED_MARKERS = (
    "전 재산",
    "매수 가격",
    "얼마에 팔",
    "무조건 오른",
    "무조건 오를",
    "수익 보장",
    "수익을 보장",
    "수익이 얼마나",
    "확실하게 말해",
    "내일 오를 종목",
    "내일 오르는 종목",
    "종목을 추천",
    "종목 추천",
)

_SERVICE_KNOWLEDGE_MARKERS = (
    "투자심리 점수",
    "positive와 negative 모델",
    "모델은 어떻게 달라",
    "모델 점수 계산",
    "미래 주가를 예측",
    "model_date",
)

_STOCK_METRIC_MARKERS = (
    "댓글 수",
    "텍스트 점수",
    "기여 키워드",
    "매수량",
    "매도량",
    "수급지수",
)

_STOCK_ANALYSIS_MARKERS = (
    "근거가 뭐",
    "해석된 이유",
    "결과를 비교",
    "수급의 관계",
    "댓글 신호",
    "수급 신호",
    "분석 요약",
    "분석 내용을 요약",
    "대표 댓글",
    "점수에 어떤 영향",
)

_STOCK_METRIC_FIELDS = {
    "매수량": (
        "individual_buy_volume",
        "확정 개인투자자 매수량",
        "주",
    ),
    "매도량": (
        "individual_sell_volume",
        "확정 개인투자자 매도량",
        "주",
    ),
    "수급지수": (
        "supply_demand_index",
        "확정 개인투자자 수급지수",
        None,
    ),
}

_STOCK_METRICS_BY_NAME = {
    "individual_buy_volume": _STOCK_METRIC_FIELDS["매수량"],
    "individual_sell_volume": _STOCK_METRIC_FIELDS["매도량"],
    "supply_demand_index": _STOCK_METRIC_FIELDS["수급지수"],
}

_STOCK_METRIC_ALIASES = {
    "매수가 가장": "매수량",
    "매수 순위": "매수량",
    "매도가 가장": "매도량",
    "매도 순위": "매도량",
    "수급지수가 가장": "수급지수",
    "수급지수 순위": "수급지수",
}


_STOCK_METRIC_RANKING_MARKERS = (
    "가장 높",
    "가장 많",
    "최대",
    "1위",
    "순위",
)


_RANKING_STORAGE_METRICS = {
    "individual_buy_volume": "buy_volume",
    "individual_sell_volume": "sell_volume",
    "supply_demand_index": "supply_demand_index",
}


def _resolve_stock_metric(
    message: str,
) -> tuple[str, str, str | None] | None:
    """사용자 질문을 허용된 확정 수급 필드로 변환한다."""

    cleaned_message = message.strip().lower()

    for marker, definition in _STOCK_METRIC_FIELDS.items():
        if marker in cleaned_message:
            return definition

    for alias, canonical_marker in (
        _STOCK_METRIC_ALIASES.items()
    ):
        if alias in cleaned_message:
            return _STOCK_METRIC_FIELDS[
                canonical_marker
            ]

    return None


def _is_stock_metric_ranking(
    message: str,
) -> bool:
    """한 종목의 값이 아니라 여러 종목의 순위를 묻는지 확인한다."""

    cleaned_message = message.strip().lower()

    return any(
        marker in cleaned_message
        for marker in _STOCK_METRIC_RANKING_MARKERS
    )


_SECURITY_RESTRICTED_MARKERS = (
    "이전 지시를 무시",
    "지시를 무시",
    "시스템 프롬프트",
    "내부 프롬프트",
    "시스템 메시지",
    "api key",
    "api_key",
    "환경변수",
    "환경 변수",
    ".env",
    "비밀정보",
    "db 비밀번호",
    "데이터베이스 비밀번호",
    "sql 실행",
    "sql을 실행",
    "python 함수를 실행",
    "파이썬 함수를 실행",
    "파일 경로",
    "chroma collection",
    "chroma 컬렉션",
)

_RESTRICTED_MARKERS = (
    _INVESTMENT_RESTRICTED_MARKERS
    + _SECURITY_RESTRICTED_MARKERS
)

_INVESTMENT_RESTRICTED_ANSWER = (
    "PILOS는 특정 종목의 매수·매도 시점이나 "
    "미래 수익을 보장하지 않습니다. "
    "저장된 분석 결과와 지표의 의미는 설명할 수 있습니다."
)

_INVESTMENT_RESTRICTED_WARNING = (
    "이 답변은 투자 권고나 수익 보장이 아닙니다."
)

_SECURITY_RESTRICTED_ANSWER = (
    "PILOS는 시스템 프롬프트, 인증정보, 환경변수와 "
    "내부 경로를 공개하지 않습니다. "
    "사용자가 지정한 SQL·Python 명령도 실행하지 않습니다. "
    "허용된 분석 조회와 서비스 설명만 제공할 수 있습니다."
)

_SECURITY_RESTRICTED_WARNING = (
    "내부 설정·비밀정보·임의 명령은 "
    "공개하거나 실행하지 않습니다."
)

_GENERAL_ANSWER = (
    "안녕하세요. PILOS 챗봇입니다. "
    "종목별 분석 결과, 정확한 수치, "
    "투자심리 점수의 의미를 질문할 수 있습니다."
)

def _restricted_response_content(
    message: str,
) -> tuple[str, str]:
    """제한 요청의 종류에 맞는 공개 답변과 warning을 선택한다."""

    cleaned_message = message.strip().lower()

    if _contains_any(
        cleaned_message,
        _SECURITY_RESTRICTED_MARKERS,
    ):
        return (
            _SECURITY_RESTRICTED_ANSWER,
            _SECURITY_RESTRICTED_WARNING,
        )

    return (
        _INVESTMENT_RESTRICTED_ANSWER,
        _INVESTMENT_RESTRICTED_WARNING,
    )


def classify_chat_route(message: str) -> ChatRoute:
    """사용자 질문이 어느 챗봇 기능으로 가야 하는지 결정한다."""

    cleaned_message = message.strip().lower()

    if not cleaned_message:
        raise ValueError("챗봇 message는 비어 있을 수 없습니다.")

    # 안전 규칙은 다른 모든 기능보다 먼저 검사한다.
    if _contains_any(cleaned_message, _RESTRICTED_MARKERS):
        return "restricted"

    # 모델과 서비스 자체의 의미를 묻는 질문이다.
    if _contains_any(
        cleaned_message,
        _SERVICE_KNOWLEDGE_MARKERS,
    ):
        return "service_knowledge"

    # DB에 저장된 정확한 숫자를 묻는 질문이다.
    if (
        _resolve_stock_metric(cleaned_message)
        is not None
        or _contains_any(
            cleaned_message,
            _STOCK_METRIC_MARKERS,
        )
    ):
        return "stock_metric"

    # 저장된 보고서의 이유와 근거를 묻는 질문이다.
    if _contains_any(
        cleaned_message,
        _STOCK_ANALYSIS_MARKERS,
    ):
        return "stock_analysis"

    # 어느 전문 경로에도 해당하지 않으면 일반 대화다.
    return "general"


def resolve_chat_route(request: ChatRequestDTO) -> ChatRoute:
    """서버에 등록된 블록과 일치하는 요청을 기능 경로로 보낸다."""

    if request.block_key is not None:
        definition = get_chat_block_definition(request.block_key)
        if definition is None:
            raise ValueError("허용되지 않은 챗봇 질문 블록입니다.")
        if (
            (request.action is not None and request.action != definition.action)
            or (request.metric is not None and request.metric != definition.metric)
            or (request.message and request.message != definition.message)
        ):
            raise ValueError("챗봇 질문 블록의 서버 계약이 일치하지 않습니다.")
        return cast(ChatRoute, definition.action)

    if request.message and _contains_any(request.message.strip().lower(), _RESTRICTED_MARKERS):
        return "restricted"

    if request.action is not None:
        return cast(ChatRoute, request.action)

    return classify_chat_route(request.message)


def _contains_any(
    message: str,
    markers: tuple[str, ...],
) -> bool:
    """질문에 지정된 표현이 하나라도 포함됐는지 검사한다."""

    return any(
        marker in message
        for marker in markers
    )

class ChatbotService:
    """챗봇의 질문 경로별 사용 사례를 조합한다."""

    def __init__(
        self,
        *,
        service_knowledge_answer: ServiceKnowledgeAnswer = (
            generate_service_knowledge_answer
        ),
        stock_analysis_answer: StockAnalysisAnswer = (
            _generate_stock_analysis_answer
        ),
        confirmed_supply_demand_lookup: (
            ConfirmedSupplyDemandLookup
        ) = select_confirmed_supply_demand,
        confirmed_supply_demand_ranking_lookup: (
            ConfirmedSupplyDemandRankingLookup
        ) = select_confirmed_supply_demand_ranking,
    ) -> None:
        self._service_knowledge_answer = (
            service_knowledge_answer
        )
        self._stock_analysis_answer = (
            stock_analysis_answer
        )
        self._confirmed_supply_demand_lookup = (
            confirmed_supply_demand_lookup
        )
        self._confirmed_supply_demand_ranking_lookup = (
            confirmed_supply_demand_ranking_lookup
        )

    def answer(
        self,
        request: ChatRequestDTO,) -> ChatResponseDTO:
        """질문을 분류하고 해당 기능으로 전달한다."""

        route = resolve_chat_route(request)

        if route == "restricted":
            answer, warning = _restricted_response_content(
                request.message
            )

            return ChatResponseDTO(
                status="ready",
                answer=answer,
                route="restricted",
                session_id=request.session_id,
                stock_code=request.stock_code,
                sources=(),
                warnings=(warning,),
            )

        if route == "service_knowledge":
            return self.answer_service_knowledge(request)

        if route in {
            "stock_metric",
            "stock_analysis",
        }:
            is_ranking_question = (
                route == "stock_metric"
                and _is_stock_metric_ranking(
                    request.message
                )
            )

            missing_fields: list[str] = []

            if (
                not is_ranking_question
                and (
                    request.stock_code is None
                    or not request.stock_code.strip()
                )
            ):
                missing_fields.append("stock_code")

            if request.model_date is None:
                missing_fields.append("model_date")

            if missing_fields:
                joined_fields = ", ".join(missing_fields)

                return ChatResponseDTO(
                    status="needs_clarification",
                    answer=(
                        "종목 질문을 처리하려면 "
                        f"{joined_fields}가 필요합니다."
                    ),
                    route=route,
                    session_id=request.session_id,
                    stock_code=request.stock_code,
                    warnings=(
                        "종목이나 날짜를 추측하지 않았습니다.",
                    ),
                )
            if route == "stock_analysis":
                return self.answer_stock_analysis(request)

            if is_ranking_question:
                return self.answer_stock_metric_ranking(
                    request
                )

            return self.answer_stock_metric(request)

        return ChatResponseDTO(
            status="ready",
            answer=_GENERAL_ANSWER,
            route="general",
            session_id=request.session_id,
            stock_code=request.stock_code,
        )

    def answer_stock_metric(
        self,
        request: ChatRequestDTO,
    ) -> ChatResponseDTO:
        """확정된 개인투자자 수급 수치를 조회해 답한다."""

        cleaned_message = request.message.strip()

        if not cleaned_message:
            raise ValueError(
                "stock_metric message는 비어 있을 수 없습니다."
            )

        if (
            request.stock_code is None
            or not request.stock_code.strip()
        ):
            raise ValueError(
                "stock_metric stock_code가 필요합니다."
            )

        if request.model_date is None:
            raise ValueError(
                "stock_metric model_date가 필요합니다."
            )

        stock_code = request.stock_code.strip()

        if (
            not stock_code.isdigit()
            or len(stock_code) > 6
        ):
            raise ValueError(
                "stock_code는 최대 6자리 숫자여야 합니다."
            )

        normalized_stock_code = stock_code.zfill(6)
        if request.metric is not None:
            metric_definition = _STOCK_METRICS_BY_NAME.get(
                request.metric
            )
        elif request.action is None:
            metric_definition = _resolve_stock_metric(
                cleaned_message
            )
        else:
            metric_definition = None

        if metric_definition is None:
            return ChatResponseDTO(
                status=(
                    "needs_clarification"
                    if request.action == "stock_metric"
                    else "not_ready"
                ),
                answer=(
                    "정확 조회할 수급 항목을 선택해주세요."
                    if request.action == "stock_metric"
                    else (
                        "현재 정확 조회는 개인 매수량, "
                        "개인 매도량과 수급지수만 지원합니다."
                    )
                ),
                route="stock_metric",
                session_id=request.session_id,
                stock_code=normalized_stock_code,
                as_of=request.model_date,
                warnings=(
                    "허용된 metric을 임의로 추측하지 않았습니다.",
                ),
            )

        field_name, label, unit = metric_definition

        try:
            result = self._confirmed_supply_demand_lookup(
                stock_code=normalized_stock_code,
                trade_date=request.model_date,
            )
        except SupplyDemandStorageError:
            return ChatResponseDTO(
                status="unavailable",
                answer=(
                    "현재 확정 수급 데이터를 "
                    "조회할 수 없습니다."
                ),
                route="stock_metric",
                session_id=request.session_id,
                stock_code=normalized_stock_code,
                as_of=request.model_date,
                warnings=(
                    "MySQL 확정 수급 조회에 실패했습니다.",
                ),
            )

        if result is None:
            return ChatResponseDTO(
                status="not_ready",
                answer=(
                    "해당 종목과 날짜의 확정 수급 데이터가 "
                    "아직 준비되지 않았습니다."
                ),
                route="stock_metric",
                session_id=request.session_id,
                stock_code=normalized_stock_code,
                as_of=request.model_date,
                warnings=(
                    "장중 추정값을 확정값으로 대신 사용하지 않았습니다.",
                ),
            )

        if result.stock_code != normalized_stock_code:
            raise RuntimeError(
                "요청과 수급 조회 결과의 stock_code가 다릅니다."
            )

        if result.trade_date != request.model_date:
            raise RuntimeError(
                "요청과 수급 조회 결과의 trade_date가 다릅니다."
            )

        value = getattr(result, field_name)

        if unit == "주":
            displayed_value = f"{int(value):,}주"
        else:
            displayed_value = str(value)

        return ChatResponseDTO(
            status="ready",
            answer=(
                f"{result.trade_date.isoformat()} "
                f"{result.stock_code}의 {label}은 "
                f"{displayed_value}입니다."
            ),
            route="stock_metric",
            session_id=request.session_id,
            stock_code=result.stock_code,
            as_of=result.trade_date,
            sources=(
                ChatSourceDTO(
                    type="mysql_metric",
                    label=(
                        f"{result.stock_code} "
                        f"{result.trade_date.isoformat()} "
                        "확정 수급"
                    ),
                    stock_code=result.stock_code,
                    model_date=result.trade_date,
                ),
            ),
        )

    def answer_stock_metric_ranking(
        self,
        request: ChatRequestDTO,
    ) -> ChatResponseDTO:
        """기준일의 확정 수급만 사용해 종목 순위를 답한다."""

        cleaned_message = request.message.strip()

        if not cleaned_message:
            raise ValueError(
                "ranking_metric message는 비어 있을 수 없습니다."
            )

        if request.model_date is None:
            raise ValueError(
                "ranking_metric model_date가 필요합니다."
            )

        metric_definition = _resolve_stock_metric(
            cleaned_message
        )

        if metric_definition is None:
            return ChatResponseDTO(
                status="not_ready",
                answer=(
                    "현재 순위 조회는 개인 매수량, "
                    "개인 매도량과 수급지수만 지원합니다."
                ),
                route="stock_metric",
                session_id=request.session_id,
                as_of=request.model_date,
                warnings=(
                    "지원하지 않는 순위 지표를 "
                    "임의로 조회하지 않았습니다.",
                ),
            )

        field_name, label, unit = metric_definition
        storage_metric = _RANKING_STORAGE_METRICS[
            field_name
        ]

        try:
            results = (
                self._confirmed_supply_demand_ranking_lookup(
                    trade_date=request.model_date,
                    metric=storage_metric,
                    limit=1,
                )
            )
        except SupplyDemandStorageError:
            return ChatResponseDTO(
                status="unavailable",
                answer=(
                    "현재 확정 수급 순위를 "
                    "조회할 수 없습니다."
                ),
                route="stock_metric",
                session_id=request.session_id,
                as_of=request.model_date,
                warnings=(
                    "MySQL 확정 수급 순위 조회에 실패했습니다.",
                ),
            )

        if not results:
            return ChatResponseDTO(
                status="not_ready",
                answer=(
                    "해당 날짜에는 순위를 계산할 "
                    "확정 수급 데이터가 없습니다."
                ),
                route="stock_metric",
                session_id=request.session_id,
                as_of=request.model_date,
                warnings=(
                    "장중 추정값은 순위에서 제외했습니다.",
                ),
            )

        winner = results[0]

        if winner.trade_date != request.model_date:
            raise RuntimeError(
                "요청과 순위 결과의 trade_date가 다릅니다."
            )

        value = getattr(winner, field_name)

        if unit == "주":
            displayed_value = f"{int(value):,}주"
        else:
            displayed_value = str(value)

        return ChatResponseDTO(
            status="ready",
            answer=(
                f"{winner.trade_date.isoformat()} "
                f"확정 수급 기준 {label}이 가장 높은 종목은 "
                f"{winner.stock_code}이며, "
                f"{displayed_value}입니다."
            ),
            route="stock_metric",
            session_id=request.session_id,
            stock_code=winner.stock_code,
            as_of=winner.trade_date,
            sources=(
                ChatSourceDTO(
                    type="mysql_metric",
                    label=(
                        f"{winner.trade_date.isoformat()} "
                        f"{label} 종목 순위"
                    ),
                    stock_code=winner.stock_code,
                    model_date=winner.trade_date,
                ),
            ),
            warnings=(
                "해당 기준일에 확정 수급이 저장된 "
                "종목만 비교했습니다.",
            ),
        )

    def answer_service_knowledge(
        self,
        request: ChatRequestDTO,
    ) -> ChatResponseDTO:
        """서비스 설명 질문을 처리한다 (정본 캐시 우선 조회)."""
        cleaned_message = request.message.strip()

        if not cleaned_message and not request.block_key:
            raise ValueError("챗봇 message는 비어 있을 수 없습니다.")

        # 1. 15개 등록 질문 블록에 대한 정본 지식 캐시 우선 조회 (Cache-First, < 50ms)
        if request.block_key and is_cached_service_block(request.block_key):
            cached = get_cached_service_knowledge(request.block_key)
            if cached is not None:
                logger.info("정본 지식 캐시 히트: block_key=%s", request.block_key)
                sources = tuple(
                    _to_service_document_source(source)
                    for source in cached["sources"]
                )
                return ChatResponseDTO(
                    status="ready",
                    answer=cached["answer"],
                    route="service_knowledge",
                    session_id=request.session_id,
                    stock_code=request.stock_code,
                    as_of=None,
                    sources=sources,
                    warnings=tuple(cached.get("warnings", ())),
                )

        # 2. 캐시 미적용 또는 동적 자연어 질의에 대한 RAG 검색 및 LLM 처리
        try:
            result = self._service_knowledge_answer(
                cleaned_message
            )
        except ServiceKnowledgeUnavailableError as error:
            logger.warning(
                "서비스 지식 외부 단계 실패: stage=%s",
                error.stage,
            )

            return ChatResponseDTO(
                status="unavailable",
                answer=(
                    "현재 서비스 설명을 생성할 수 없습니다. "
                    "잠시 후 다시 시도해 주세요."
                ),
                route="service_knowledge",
                session_id=request.session_id,
                stock_code=request.stock_code,
                as_of=None,
                sources=(),
                warnings=(
                    "검색 또는 답변 생성 외부 서비스를 "
                    "사용할 수 없습니다.",
                ),
            )
        status = result.get("status")

        if status not in _SERVICE_KNOWLEDGE_STATUSES:
            raise RuntimeError(
                "RAG 서비스가 지원하지 않는 상태를 반환했습니다: "
                f"{status}")

        answer = result.get("answer")

        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("RAG 서비스의 answer가 비어 있습니다.")

        raw_sources = result.get("sources", [])
        if not isinstance(raw_sources, list):
            raise RuntimeError("RAG 서비스의 sources는 목록이어야 합니다.")

        sources = tuple(
            _to_service_document_source(source)
            for source in raw_sources
        )

        raw_warnings = result.get("warnings", [])
        if (not isinstance(raw_warnings, list) or not all(
            isinstance(warning, str)
            for warning in raw_warnings
        )):
            raise RuntimeError("RAG 서비스의 warnings는 문자열 목록이어야 합니다.")

        public_answer = answer.strip()
        if (
            request.block_key == "service_columns"
            or (request.block_key and request.block_key.startswith("column_"))
        ):
            public_answer = _localize_public_column_names(public_answer)

        return ChatResponseDTO(
            status=cast(ChatStatus, status),
            answer=public_answer,
            route="service_knowledge",
            session_id=request.session_id,
            stock_code=request.stock_code,
            as_of=None,
            sources=sources,
            warnings=tuple(raw_warnings),
        )

    def answer_stock_analysis(
        self,
        request: ChatRequestDTO,
    ) -> ChatResponseDTO:
        """저장된 종목 분석 보고서를 근거로 답한다."""

        cleaned_message = request.message.strip()

        if not cleaned_message:
            raise ValueError("stock_analysis message는 비어 있을 수 없습니다.")

        if (
            request.stock_code is None
            or not request.stock_code.strip()
        ):
            raise ValueError("stock_analysis stock_code가 필요합니다.")

        if request.model_date is None:
            raise ValueError("stock_analysis model_date가 필요합니다.")

        cleaned_stock_code = request.stock_code.strip()

        try:
            result = self._stock_analysis_answer(
                cleaned_message,
                cleaned_stock_code,
                request.model_date,
            )
        except StockAnalysisNotReadyError:
            return ChatResponseDTO(
                status="not_ready",
                answer=(
                    "해당 종목과 날짜의 선행 분석이 "
                    "아직 완료되지 않았습니다."
                ),
                route="stock_analysis",
                session_id=request.session_id,
                stock_code=cleaned_stock_code,
                warnings=(
                    "보고서 생성 전 상태입니다.",
                ),
            )
        except StockAnalysisNotFoundError:
            return ChatResponseDTO(
                status="not_found",
                answer=(
                    "해당 종목과 날짜의 "
                    "분석 보고서를 찾지 못했습니다."
                ),
                route="stock_analysis",
                session_id=request.session_id,
                stock_code=cleaned_stock_code,
            )
        except StockAnalysisServiceError:
            return ChatResponseDTO(
                status="unavailable",
                answer=(
                    "현재 분석 보고서를 "
                    "조회할 수 없습니다."
                ),
                route="stock_analysis",
                session_id=request.session_id,
                stock_code=cleaned_stock_code,
                warnings=(
                    "MySQL 보고서 조회에 실패했습니다.",
                ),
            )
        if not isinstance(result, dict):
            raise RuntimeError(
                "stock_analysis 결과는 dict여야 합니다."
            )

        if result.get("status") != "ready":
            raise RuntimeError(
                "stock_analysis 결과 상태가 올바르지 않습니다."
            )

        answer = result.get("answer")
        result_stock_code = result.get("stock_code")
        result_model_date = result.get("model_date")
        raw_warnings = result.get("warnings", [])

        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(
                "stock_analysis answer가 비어 있습니다."
            )

        if (
            not isinstance(result_stock_code, str)
            or not result_stock_code.strip()
        ):
            raise RuntimeError(
                "stock_analysis stock_code가 비어 있습니다."
            )

        if not isinstance(result_model_date, date):
            raise RuntimeError(
                "stock_analysis model_date가 올바르지 않습니다."
            )

        if result_stock_code.strip() != cleaned_stock_code:
            raise RuntimeError(
                "요청과 조회 결과의 stock_code가 다릅니다."
            )

        if result_model_date != request.model_date:
            raise RuntimeError(
                "요청과 조회 결과의 model_date가 다릅니다."
            )

        if (
            not isinstance(raw_warnings, list)
            or not all(
                isinstance(warning, str)
                for warning in raw_warnings
            )
        ):
            raise RuntimeError(
                "stock_analysis warnings가 올바르지 않습니다."
            )

        return ChatResponseDTO(
            status="ready",
            answer=answer.strip(),
            route="stock_analysis",
            session_id=request.session_id,
            stock_code=result_stock_code.strip(),
            as_of=result_model_date,
            sources=(
                ChatSourceDTO(
                    type="llm_report",
                    label=(
                        f"{result_stock_code.strip()} "
                        f"{result_model_date.isoformat()} "
                        "분석 보고서"
                    ),
                    stock_code=result_stock_code.strip(),
                    model_date=result_model_date,
                ),
            ),
            warnings=tuple(raw_warnings),
        )

def _to_service_document_source(source: Any) -> ChatSourceDTO:
    """RAG 내부 출처에서 공개 가능한 필드만 선택한다."""

    if not isinstance(source, dict):
        raise RuntimeError("RAG 출처는 object 형식이어야 합니다.")

    source_type = source.get("type")
    label = source.get("label")
    version = source.get("version")

    if source_type != "service_document":
        raise RuntimeError(
            "서비스 지식 답변에는 service_document "
            "출처만 사용할 수 있습니다.")

    if not isinstance(label, str) or not label.strip():
        raise RuntimeError("RAG 출처의 공개 label이 비어 있습니다.")

    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(
            "RAG 출처의 공개 version이 비어 있습니다."
        )

    return ChatSourceDTO(
        type="service_document",
        label=label.strip(),
        version=version.strip()
    )
