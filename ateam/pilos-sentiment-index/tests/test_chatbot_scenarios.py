import unittest

from datetime import date, datetime
from unittest.mock import Mock

from pilos.dto.chat_dto import ChatRequestDTO
from pilos.dto.supply_demand_dto import (
    ConfirmedSupplyDemand,
    SupplyDemandStorageError,
)
from pilos.service.chatbot_service import (
    ChatbotService,
    StockAnalysisNotFoundError,
    StockAnalysisNotReadyError,
    StockAnalysisServiceError,
)
from pilos.service.rag_service import (
    ServiceKnowledgeUnavailableError,
)


_MODEL_DATE = date(2026, 8, 5)
_CONFIRMED_SUPPLY = ConfirmedSupplyDemand(
    stock_code="005930",
    trade_date=_MODEL_DATE,
    individual_buy_volume=1500,
    individual_sell_volume=1000,
    supply_demand_index=0.2,
    observed_at=datetime(2026, 8, 5, 16, 0),
    source_api="ka10060",
)


def _ready_service() -> ChatbotService:
    """정상 route가 외부 시스템 없이 실행되는 서비스를 만든다."""

    return ChatbotService(
        confirmed_supply_demand_lookup=Mock(
            return_value=_CONFIRMED_SUPPLY
        ),
        stock_analysis_answer=Mock(
            return_value={
                "status": "ready",
                "answer": "저장된 v13 보고서 분석입니다.",
                "stock_code": "005930",
                "model_date": _MODEL_DATE,
                "warnings": ["투자 권고가 아닙니다."],
            }
        ),
        service_knowledge_answer=Mock(
            return_value={
                "status": "ready",
                "answer": "model_date는 분석 기준 거래일입니다.",
                "route": "service_knowledge",
                "sources": [
                    {
                        "type": "service_document",
                        "label": "PILOS 서비스 안내",
                        "version": "1.0",
                    }
                ],
                "warnings": [],
            }
        ),
    )


class ChatbotScenarioTest(unittest.TestCase):
    def assert_public_response_consistent(
        self,
        response,
        *,
        expected_route,
        expected_status,
        expected_source_type=None,
    ):
        """공개 상태·답변·출처가 한 시나리오 안에서 일치하는지 본다."""

        self.assertEqual(response.route, expected_route)
        self.assertEqual(response.status, expected_status)
        self.assertTrue(response.answer.strip())

        if expected_source_type is None:
            self.assertEqual(response.sources, ())
        else:
            self.assertTrue(response.sources)
            self.assertEqual(
                response.sources[0].type,
                expected_source_type,
            )

    def test_ready_routes_use_expected_public_sources(self):
        service = _ready_service()
        scenarios = (
            (
                ChatRequestDTO(
                    action="stock_metric",
                    metric="individual_buy_volume",
                    message="확정 개인 매수량을 알려줘.",
                    stock_code="005930",
                    model_date=_MODEL_DATE,
                ),
                "stock_metric",
                "mysql_metric",
            ),
            (
                ChatRequestDTO(
                    action="stock_metric",
                    metric="individual_sell_volume",
                    message="확정 개인 매도량을 알려줘.",
                    stock_code="005930",
                    model_date=_MODEL_DATE,
                ),
                "stock_metric",
                "mysql_metric",
            ),
            (
                ChatRequestDTO(
                    action="stock_metric",
                    metric="supply_demand_index",
                    message="확정 수급지수를 알려줘.",
                    stock_code="005930",
                    model_date=_MODEL_DATE,
                ),
                "stock_metric",
                "mysql_metric",
            ),
            (
                ChatRequestDTO(
                    action="stock_analysis",
                    message="오늘 분석 내용을 요약해줘.",
                    stock_code="005930",
                    model_date=_MODEL_DATE,
                ),
                "stock_analysis",
                "llm_report",
            ),
            (
                ChatRequestDTO(
                    action="service_knowledge",
                    message="model_date는 무슨 날짜야?",
                ),
                "service_knowledge",
                "service_document",
            ),
            (
                ChatRequestDTO(message="안녕하세요."),
                "general",
                None,
            ),
            (
                ChatRequestDTO(
                    action="stock_analysis",
                    message="삼성전자 매수 가격을 정해줘.",
                    stock_code="005930",
                    model_date=_MODEL_DATE,
                ),
                "restricted",
                None,
            ),
        )

        for request, route, source_type in scenarios:
            with self.subTest(route=route, message=request.message):
                response = service.answer(request)

                self.assert_public_response_consistent(
                    response,
                    expected_route=route,
                    expected_status="ready",
                    expected_source_type=source_type,
                )

    def test_missing_context_and_metric_request_clarification(self):
        service = _ready_service()
        requests = (
            ChatRequestDTO(
                action="stock_metric",
                metric="individual_buy_volume",
                message="개인 매수량을 알려줘.",
                model_date=_MODEL_DATE,
            ),
            ChatRequestDTO(
                action="stock_metric",
                metric="individual_buy_volume",
                message="개인 매수량을 알려줘.",
                stock_code="005930",
            ),
            ChatRequestDTO(
                action="stock_metric",
                message="선택한 수치를 알려줘.",
                stock_code="005930",
                model_date=_MODEL_DATE,
            ),
        )

        for request in requests:
            with self.subTest(message=request.message):
                response = service.answer(request)

                self.assert_public_response_consistent(
                    response,
                    expected_route="stock_metric",
                    expected_status="needs_clarification",
                )
                self.assertTrue(response.warnings)

    def test_confirmed_supply_states_have_no_source(self):
        request = ChatRequestDTO(
            action="stock_metric",
            metric="supply_demand_index",
            message="확정 수급지수를 알려줘.",
            stock_code="005930",
            model_date=_MODEL_DATE,
        )
        cases = (
            (None, "not_ready"),
            (SupplyDemandStorageError(), "unavailable"),
        )

        for result_or_error, expected_status in cases:
            with self.subTest(status=expected_status):
                lookup = Mock()

                if isinstance(result_or_error, Exception):
                    lookup.side_effect = result_or_error
                else:
                    lookup.return_value = result_or_error

                response = ChatbotService(
                    confirmed_supply_demand_lookup=lookup,
                ).answer(request)

                self.assert_public_response_consistent(
                    response,
                    expected_route="stock_metric",
                    expected_status=expected_status,
                )
                self.assertTrue(response.warnings)

    def test_stock_analysis_states_have_no_source(self):
        request = ChatRequestDTO(
            action="stock_analysis",
            message="오늘 분석 내용을 요약해줘.",
            stock_code="005930",
            model_date=_MODEL_DATE,
        )
        cases = (
            (StockAnalysisNotReadyError(), "not_ready"),
            (StockAnalysisNotFoundError(), "not_found"),
            (StockAnalysisServiceError(), "unavailable"),
        )

        for error, expected_status in cases:
            with self.subTest(status=expected_status):
                response = ChatbotService(
                    stock_analysis_answer=Mock(
                        side_effect=error
                    ),
                ).answer(request)

                self.assert_public_response_consistent(
                    response,
                    expected_route="stock_analysis",
                    expected_status=expected_status,
                )

    def test_service_knowledge_states_have_no_source(self):
        request = ChatRequestDTO(
            action="service_knowledge",
            message="model_date는 무슨 날짜야?",
        )
        dependencies = (
            (
                Mock(
                    return_value={
                        "status": "not_found",
                        "answer": "관련 문서를 찾지 못했습니다.",
                        "route": "service_knowledge",
                        "sources": [],
                        "warnings": [
                            "검색 결과가 없어 LLM을 호출하지 않았습니다."
                        ],
                    }
                ),
                "not_found",
            ),
            (
                Mock(
                    side_effect=ServiceKnowledgeUnavailableError(
                        "embedding"
                    )
                ),
                "unavailable",
            ),
        )

        for dependency, expected_status in dependencies:
            with self.subTest(status=expected_status):
                service = ChatbotService(
                    service_knowledge_answer=dependency,
                )

                if expected_status == "unavailable":
                    with self.assertLogs(
                        "pilos.service.chatbot_service",
                        level="WARNING",
                    ) as captured:
                        response = service.answer(request)

                    self.assertIn(
                        "stage=embedding",
                        "\n".join(captured.output),
                    )
                else:
                    response = service.answer(request)

                self.assert_public_response_consistent(
                    response,
                    expected_route="service_knowledge",
                    expected_status=expected_status,
                )
                self.assertTrue(response.warnings)


if __name__ == "__main__":
    unittest.main()
