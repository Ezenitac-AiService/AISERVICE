import unittest

from dataclasses import FrozenInstanceError
from datetime import date

from pilos.dto.chat_dto import (
    ChatRequestDTO,
    ChatResponseDTO,
    ChatSourceDTO,
)


class ChatDtoTest(unittest.TestCase):
    def test_request_keeps_optional_stock_context(self):
        request = ChatRequestDTO(
            message="삼성전자 점수가 왜 이렇게 나왔나요?",
            action="stock_analysis",
            session_id="session-1",
            stock_code="005930",
            model_date=date(2026, 8, 5),
        )

        self.assertEqual(
            request.message,
            "삼성전자 점수가 왜 이렇게 나왔나요?",
        )
        self.assertEqual(request.action, "stock_analysis")
        self.assertIsNone(request.metric)
        self.assertEqual(request.session_id, "session-1")
        self.assertEqual(request.stock_code, "005930")
        self.assertEqual(
            request.model_date,
            date(2026, 8, 5),
        )

    def test_response_contains_only_public_source_fields(self):
        source = ChatSourceDTO(
            type="service_document",
            label="PILOS 서비스 안내",
        )

        response = ChatResponseDTO(
            status="ready",
            answer=(
                "model_date는 모델 분석의 "
                "기준 거래일입니다."
            ),
            route="service_knowledge",
            sources=(source,),
        )

        self.assertEqual(response.status, "ready")
        self.assertEqual(
            response.route,
            "service_knowledge",
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

    def test_response_is_immutable_and_has_safe_defaults(self):
        response = ChatResponseDTO(
            status="not_found",
            answer="관련 근거를 찾지 못했습니다.",
            route="service_knowledge",
        )

        self.assertEqual(response.sources, ())
        self.assertEqual(response.warnings, ())

        with self.assertRaises(FrozenInstanceError):
            response.answer = "변경된 답변"


if __name__ == "__main__":
    unittest.main()
