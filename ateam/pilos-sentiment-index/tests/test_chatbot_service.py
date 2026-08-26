import unittest

from datetime import date, datetime
from unittest.mock import Mock, patch

from pilos.dto.supply_demand_dto import (
    ConfirmedSupplyDemand,
    SupplyDemandStorageError,
)

from pilos.dto.chat_dto import (
    ChatRequestDTO,
    ChatResponseDTO,
)
from pilos.service.chatbot_service import (
    ChatbotService,
    StockAnalysisNotFoundError,
    StockAnalysisNotReadyError,
    StockAnalysisServiceError,
)
from pilos.service.llm_report_service import (
    LLMReportGenerationPendingError,
    LLMReportInferencePendingError,
)
from pilos.service.rag_service import (
    ServiceKnowledgeUnavailableError,
)

_CONFIRMED_SUPPLY = ConfirmedSupplyDemand(
    stock_code="005930",
    trade_date=date(2026, 8, 5),
    individual_buy_volume=1500,
    individual_sell_volume=1000,
    supply_demand_index=0.2,
    observed_at=datetime(2026, 8, 5, 16, 0),
    source_api="ka10060",
)

class ChatbotServiceTest(unittest.TestCase):
    def test_service_knowledge_result_becomes_response_dto(
        self,
    ):
        rag_answer = Mock(
            return_value={
                "status": "ready",
                "answer": (
                    "model_date는 모델 분석의 "
                    "기준 거래일입니다."
                ),
                "route": "service_knowledge",
                "sources": [
                    {
                        "type": "service_document",
                        "label": "PILOS 서비스 안내",
                        "version": "1.0",
                        "chunk_id": "internal-id",
                        "rerank_score": 0.9,
                    }
                ],
                "warnings": [],
            }
        )
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )
        request = ChatRequestDTO(
            message="model_date는 무엇인가요?",
            session_id="session-1",
        )

        response = service.answer_service_knowledge(
            request
        )

        self.assertIsInstance(
            response,
            ChatResponseDTO,
        )
        self.assertEqual(response.status, "ready")
        self.assertEqual(
            response.route,
            "service_knowledge",
        )
        self.assertEqual(
            response.session_id,
            "session-1",
        )
        self.assertEqual(len(response.sources), 1)
        self.assertEqual(
            response.sources[0].label,
            "PILOS 서비스 안내",
        )
        self.assertFalse(
            hasattr(response.sources[0], "chunk_id")
        )
        self.assertFalse(
            hasattr(response.sources[0], "rerank_score")
        )
        self.assertEqual(
            response.sources[0].version,
            "1.0",
        )

        rag_answer.assert_called_once_with(
            "model_date는 무엇인가요?"
        )

    def test_not_found_result_becomes_response_dto(
        self,
    ):
        rag_answer = Mock(
            return_value={
                "status": "not_found",
                "answer": "관련 문서를 찾지 못했습니다.",
                "route": "service_knowledge",
                "sources": [],
                "warnings": [
                    "검색 결과가 없어 LLM을 호출하지 않았습니다."
                ],
            }
        )
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        response = service.answer_service_knowledge(
            ChatRequestDTO(
                message="알 수 없는 기능은 무엇인가요?",
            )
        )

        self.assertEqual(
            response.status,
            "not_found",
        )
        self.assertEqual(response.sources, ())
        self.assertEqual(
            response.warnings,
            (
                "검색 결과가 없어 "
                "LLM을 호출하지 않았습니다.",
            ),
        )

    def test_service_knowledge_failure_becomes_unavailable(
        self,
    ):
        rag_answer = Mock(
            side_effect=ServiceKnowledgeUnavailableError(
                "embedding"
            )
        )
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        with self.assertLogs(
            "pilos.service.chatbot_service",
            level="WARNING",
        ) as captured:
            response = service.answer_service_knowledge(
                ChatRequestDTO(
                    message="model_date는 무엇인가요?",
                    session_id="session-1",
                )
            )

        self.assertEqual(response.status, "unavailable")
        self.assertEqual(response.route, "service_knowledge")
        self.assertEqual(response.session_id, "session-1")
        self.assertEqual(response.sources, ())
        self.assertTrue(response.warnings)

        self.assertIn(
            "stage=embedding",
            "\n".join(captured.output),
        )

        public_text = " ".join(
            (
                response.answer,
                *response.warnings,
            )
        )
        self.assertNotIn(
            "embedding",
            public_text,
        )

    def test_empty_message_is_rejected_before_rag_call(
        self,
    ):
        rag_answer = Mock()
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        with self.assertRaisesRegex(
            ValueError,
            "비어 있을 수 없습니다",
        ):
            service.answer_service_knowledge(
                ChatRequestDTO(
                    message="   ",
                )
            )

        rag_answer.assert_not_called()

    def test_restricted_question_does_not_call_rag(self,):
        rag_answer = Mock()
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                message="삼성전자 매수 가격을 정해줘.",
                action="service_knowledge",
                session_id="session-1",
            )
        )

        self.assertEqual(response.status, "ready")
        self.assertEqual(response.route, "restricted")
        self.assertIn("매수·매도", response.answer)
        rag_answer.assert_not_called()

    def test_explicit_action_overrides_marker_classification(
        self,
    ):
        rag_answer = Mock(
            return_value={
                "status": "ready",
                "answer": "수급지수의 의미를 설명합니다.",
                "sources": [],
                "warnings": [],
            }
        )
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                action="service_knowledge",
                message="수급지수의 의미를 설명해줘.",
            )
        )

        self.assertEqual(response.route, "service_knowledge")
        rag_answer.assert_called_once_with(
            "수급지수의 의미를 설명해줘."
        )

    def test_service_knowledge_question_calls_rag(self,):
        rag_answer = Mock(
            return_value={
                "status": "ready",
                "answer": "model_date는 분석 기준 거래일입니다.",
                "sources": [
                    {
                        "type": "service_document",
                        "label": "PILOS 서비스 안내",
                        "version": "1.0",
                    }
                ],
                "warnings": [],
            }
        )
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                message="model_date는 무슨 날짜야?",
            )
        )

        self.assertEqual(
            response.route,
            "service_knowledge",
        )
        self.assertEqual(response.status, "ready")

        rag_answer.assert_called_once_with(
            "model_date는 무슨 날짜야?"
        )

    def test_stock_question_requests_missing_context(self,):
        rag_answer = Mock()
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                message="삼성전자 댓글 수를 알려줘.",
            )
        )

        self.assertEqual(
            response.route,
            "stock_metric",
        )
        self.assertEqual(
            response.status,
            "needs_clarification",
        )
        self.assertIn(
            "stock_code",
            response.answer,
        )
        self.assertIn(
            "model_date",
            response.answer,
        )
        rag_answer.assert_not_called()

    def test_general_question_returns_basic_guide(self,):
        rag_answer = Mock()
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                message="안녕하세요.",
            )
        )

        self.assertEqual(response.status, "ready")
        self.assertEqual(response.route, "general")
        self.assertIn("PILOS", response.answer)

        rag_answer.assert_not_called()

    def test_stock_analysis_uses_saved_report(self,):
        rag_answer = Mock()
        stock_analysis_answer = Mock(
            return_value={
                "status": "ready",
                "answer": "저장된 보고서에 따른 분석입니다.",
                "stock_code": "005930",
                "model_date": date(2026, 8, 5),
                "warnings": [],
            }
        )
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
            stock_analysis_answer=stock_analysis_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                message=(
                    "삼성전자 주요 분석 내용을 요약해줘."
                ),
                session_id="session-1",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(response.status, "ready")
        self.assertEqual(
            response.route,
            "stock_analysis",
        )
        self.assertEqual(
            response.as_of,
            date(2026, 8, 5),
        )
        self.assertEqual(len(response.sources), 1)
        self.assertEqual(
            response.sources[0].type,
            "llm_report",
        )
        self.assertEqual(
            response.sources[0].stock_code,
            "005930",
        )

        stock_analysis_answer.assert_called_once_with(
            "삼성전자 주요 분석 내용을 요약해줘.",
            "005930",
            date(2026, 8, 5),
        )
        rag_answer.assert_not_called()

    @patch(
        "pilos.service.llm_report_service.get_llm_report_for_display"
    )
    def test_default_stock_analysis_uses_v13_display_report(
        self,
        get_report,
    ):
        get_report.return_value = {
            "stock_code": "005930",
            "stock_name": "삼성전자",
            "model_date": "2026-08-05",
            "supply_direction": "SELL",
            "actual_supply_index": -0.02,
            "comment_signal_score": 61,
            "signal_level": "높음",
            "signal_status": "ready",
            "signal_change": 4,
            "signal_ma5": 57,
            "comment_count": 2409,
            "market_commentary": (
                "현재 댓글 수급 신호는 높은 편입니다."
            ),
            "conclusion": "직전 거래일보다 4점 높습니다.",
            "notice": "투자 권고가 아닙니다.",
        }
        service = ChatbotService()

        response = service.answer(
            ChatRequestDTO(
                action="stock_analysis",
                message="선택한 분석을 요약해줘.",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(response.status, "ready")
        self.assertIn("높은 편", response.answer)
        self.assertIn("투자 권고가 아닙니다", response.answer)
        self.assertEqual(response.sources[0].type, "llm_report")
        get_report.assert_called_once_with(
            "005930",
            date(2026, 8, 5),
        )

    @patch(
        "pilos.service.llm_report_service.get_llm_report_for_display"
    )
    def test_report_pending_states_become_chatbot_not_ready(
        self,
        get_report,
    ):
        pending_errors = (
            LLMReportInferencePendingError("inference pending"),
            LLMReportGenerationPendingError("report pending"),
        )

        for pending_error in pending_errors:
            with self.subTest(error=type(pending_error).__name__):
                get_report.reset_mock()
                get_report.side_effect = pending_error
                service = ChatbotService()

                response = service.answer(
                    ChatRequestDTO(
                        action="stock_analysis",
                        message="선택한 분석을 요약해줘.",
                        stock_code="005930",
                        model_date=date(2026, 8, 5),
                    )
                )

                self.assertEqual(response.status, "not_ready")
                self.assertEqual(response.route, "stock_analysis")
                self.assertEqual(response.sources, ())
                get_report.assert_called_once_with(
                    "005930",
                    date(2026, 8, 5),
                )

    def test_stock_analysis_not_ready_is_preserved(
        self,
    ):
        stock_analysis_answer = Mock(
            side_effect=StockAnalysisNotReadyError()
        )
        service = ChatbotService(
            stock_analysis_answer=stock_analysis_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                message="주요 분석 내용을 요약해줘.",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(
            response.status,
            "not_ready",
        )
        self.assertEqual(
            response.route,
            "stock_analysis",
        )
        self.assertIsNone(response.as_of)

    def test_stock_analysis_not_found_is_preserved(
        self,
    ):
        stock_analysis_answer = Mock(
            side_effect=StockAnalysisNotFoundError()
        )
        service = ChatbotService(
            stock_analysis_answer=stock_analysis_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                message="주요 분석 내용을 요약해줘.",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(
            response.status,
            "not_found",
        )
        self.assertEqual(response.sources, ())


    def test_stock_analysis_db_failure_is_unavailable(self,):
        stock_analysis_answer = Mock(
            side_effect=StockAnalysisServiceError()
        )
        service = ChatbotService(
            stock_analysis_answer=stock_analysis_answer,
        )

        response = service.answer(
            ChatRequestDTO(
                message="주요 분석 내용을 요약해줘.",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(
            response.status,
            "unavailable",
        )
        self.assertIn(
            "MySQL",
            response.warnings[0],
        )

    def test_explicit_stock_metric_uses_selected_metric(
        self,
    ):
        lookup = Mock(
            return_value=_CONFIRMED_SUPPLY
        )
        service = ChatbotService(
            confirmed_supply_demand_lookup=lookup,
        )

        response = service.answer(
            ChatRequestDTO(
                action="stock_metric",
                metric="individual_buy_volume",
                message="선택한 값을 알려줘.",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(response.status, "ready")
        self.assertIn("1,500주", response.answer)
        lookup.assert_called_once_with(
            stock_code="005930",
            trade_date=date(2026, 8, 5),
        )

    def test_explicit_stock_metric_does_not_infer_missing_metric(
        self,
    ):
        lookup = Mock()
        service = ChatbotService(
            confirmed_supply_demand_lookup=lookup,
        )

        response = service.answer(
            ChatRequestDTO(
                action="stock_metric",
                message="개인 매수량은 얼마야?",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(
            response.status,
            "needs_clarification",
        )
        self.assertIn("선택", response.answer)
        lookup.assert_not_called()
    def test_supported_stock_metrics_use_confirmed_data(self,):
        cases = (
            (
                "개인 매수량은 얼마야?",
                "1,500주",
            ),
            (
                "개인 매도량은 얼마야?",
                "1,000주",
            ),
            (
                "실제 수급지수를 알려줘.",
                "0.2",
            ),
        )

        for message, expected_value in cases:
            with self.subTest(message=message):
                lookup = Mock(
                    return_value=_CONFIRMED_SUPPLY
                )
                service = ChatbotService(
                    confirmed_supply_demand_lookup=lookup,
                )

                response = service.answer(
                    ChatRequestDTO(
                        message=message,
                        stock_code="005930",
                        model_date=date(2026, 8, 5),
                    )
                )

                self.assertEqual(response.status, "ready")
                self.assertEqual(
                    response.route,
                    "stock_metric",
                )
                self.assertIn(
                    expected_value,
                    response.answer,
                )
                self.assertEqual(
                    response.as_of,
                    date(2026, 8, 5),
                )
                self.assertEqual(
                    response.sources[0].type,
                    "mysql_metric",
                )

                lookup.assert_called_once_with(
                    stock_code="005930",
                    trade_date=date(2026, 8, 5),
                )


    def test_missing_confirmed_supply_is_not_ready(self):
        lookup = Mock(return_value=None)
        service = ChatbotService(
            confirmed_supply_demand_lookup=lookup,
        )

        response = service.answer(
            ChatRequestDTO(
                message="개인 매수량은 얼마야?",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(response.status, "not_ready")
        self.assertEqual(response.sources, ())
        self.assertIn(
            "추정값",
            response.warnings[0],
        )


    def test_supply_storage_failure_is_unavailable(self):
        lookup = Mock(
            side_effect=SupplyDemandStorageError()
        )
        service = ChatbotService(
            confirmed_supply_demand_lookup=lookup,
        )

        response = service.answer(
            ChatRequestDTO(
                message="실제 수급지수를 알려줘.",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(
            response.status,
            "unavailable",
        )
        self.assertIn(
            "MySQL",
            response.warnings[0],
        )


    def test_unsupported_metric_does_not_query_supply(self):
        lookup = Mock()
        service = ChatbotService(
            confirmed_supply_demand_lookup=lookup,
        )

        response = service.answer(
            ChatRequestDTO(
                message="댓글 수를 알려줘.",
                stock_code="005930",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(response.status, "not_ready")
        lookup.assert_not_called()

    def test_ranking_question_uses_confirmed_rows(
        self,
    ):
        exact_lookup = Mock()
        ranking_lookup = Mock(
            return_value=[_CONFIRMED_SUPPLY]
        )
        service = ChatbotService(
            confirmed_supply_demand_lookup=exact_lookup,
            confirmed_supply_demand_ranking_lookup=(
                ranking_lookup
            ),
        )

        response = service.answer(
            ChatRequestDTO(
                message=(
                    "개인 매수량이 가장 높은 종목은?"
                ),
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(response.status, "ready")
        self.assertEqual(response.route, "stock_metric")
        self.assertEqual(
            response.stock_code,
            "005930",
        )
        self.assertIn("1,500주", response.answer)
        self.assertEqual(
            response.sources[0].type,
            "mysql_metric",
        )

        ranking_lookup.assert_called_once_with(
            trade_date=date(2026, 8, 5),
            metric="buy_volume",
            limit=1,
        )
        exact_lookup.assert_not_called()

    def test_ranking_requires_date_not_stock_code(self):
        ranking_lookup = Mock()
        service = ChatbotService(
            confirmed_supply_demand_ranking_lookup=(
                ranking_lookup
            ),
        )

        response = service.answer(
            ChatRequestDTO(
                message=(
                    "개인 매수량이 가장 높은 종목은?"
                ),
            )
        )

        self.assertEqual(
            response.status,
            "needs_clarification",
        )
        self.assertIn("model_date", response.answer)
        self.assertNotIn("stock_code", response.answer)
        ranking_lookup.assert_not_called()

    def test_empty_confirmed_ranking_is_not_ready(self):
        ranking_lookup = Mock(return_value=[])
        service = ChatbotService(
            confirmed_supply_demand_ranking_lookup=(
                ranking_lookup
            ),
        )

        response = service.answer(
            ChatRequestDTO(
                message="매수가 가장 높은 종목은?",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(response.status, "not_ready")
        self.assertIn(
            "추정값",
            response.warnings[0],
        )

    def test_ranking_storage_failure_is_unavailable(self):
        ranking_lookup = Mock(
            side_effect=SupplyDemandStorageError()
        )
        service = ChatbotService(
            confirmed_supply_demand_ranking_lookup=(
                ranking_lookup
            ),
        )

        response = service.answer(
            ChatRequestDTO(
                message="매도량 순위 1위는?",
                model_date=date(2026, 8, 5),
            )
        )

        self.assertEqual(
            response.status,
            "unavailable",
        )
    def test_cached_service_knowledge_block_returns_without_calling_rag(self):
        rag_answer = Mock()
        service = ChatbotService(
            service_knowledge_answer=rag_answer,
        )

        response = service.answer_service_knowledge(
            ChatRequestDTO(
                block_key="service_overview",
                message="PILOS 서비스 개요가 무엇인가요?",
                action="service_knowledge",
                session_id="session-cache-test",
            )
        )

        self.assertEqual(response.status, "ready")
        self.assertEqual(response.route, "service_knowledge")
        self.assertIn("온라인 종목 토론방", response.answer)
        self.assertEqual(response.sources[0].label, "PILOS 서비스 문서")
        self.assertEqual(response.sources[0].version, "1.0")
        # RAG or LLM must NOT be called for cached blocks!
        rag_answer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
