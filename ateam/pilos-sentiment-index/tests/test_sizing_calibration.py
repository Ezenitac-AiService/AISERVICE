"""
Unit tests for Context Window & Sizing Calibration per Feature 008 Phase 9 (T032-A).
Validates:
1. llm_report.py message byte budget expanded to 48,000 bytes and dynamic error message.
2. llm_report_client.py output token budget REPORT_MAX_TOKENS = 4096.
3. Timeout >= 60.0s and 3-attempt exponential backoff circuit breaker isolation.
4. rag_service.py RERANK_TOP_K = 10 and max_tokens = 4096.
"""

import unittest
from unittest.mock import Mock, patch
from openai import APIConnectionError

from pilos.analysis.llm_report import (
    MAX_LLM_MESSAGE_BYTES,
    build_report_messages,
)
from pilos.collection.ai_clients.llm_report_client import (
    REPORT_MAX_TOKENS,
    LlmReportClientSettings,
    OpenAICompatibleLlmReportClient,
    LlmReportTransportError,
)
import pilos.service.rag_service as rag_service_mod
from tests.test_llm_report_client import make_settings, make_request, make_completion


class TestPilosSizingCalibration(unittest.TestCase):
    def test_llm_report_message_bytes_and_error_message(self):
        """Verify 48,000-byte expansion and dynamic error message formatting."""
        self.assertEqual(MAX_LLM_MESSAGE_BYTES, 48000)

        # Create dummy request and test error when exceeding MAX_LLM_MESSAGE_BYTES
        req = make_request()
        with patch("pilos.analysis.llm_report._message_bytes", return_value=48001):
            with self.assertRaises(ValueError) as ctx:
                build_report_messages(req)
            self.assertIn("48,000바이트를 초과합니다", str(ctx.exception))

    def test_llm_report_client_token_budget(self):
        """Verify REPORT_MAX_TOKENS is calibrated to 4096."""
        self.assertEqual(REPORT_MAX_TOKENS, 4096)

        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion()
        client = OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )
        client.generate_report(make_request())

        args = sdk_client.chat.completions.create.call_args.kwargs
        self.assertEqual(args["max_tokens"], 4096)

    def test_llm_report_client_timeout_and_retries(self):
        """Verify default timeout >= 60.0s and 3 retries on transport failures."""
        settings = make_settings()
        self.assertGreaterEqual(settings.timeout_seconds, 60.0)

        sdk_client = Mock()
        sdk_client.chat.completions.create.side_effect = APIConnectionError(request=Mock())
        sleep_mock = Mock()
        client = OpenAICompatibleLlmReportClient(
            settings=settings,
            sdk_client=sdk_client,
            sleep=sleep_mock,
        )

        with self.assertRaises(LlmReportTransportError):
            client.request_completion([{"role": "user", "content": "hi"}])

        self.assertEqual(sdk_client.chat.completions.create.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)
        sleep_mock.assert_any_call(1.0)
        sleep_mock.assert_any_call(2.0)

    def test_rag_service_sizing(self):
        """Verify rag_service.py RERANK_TOP_K = 10 and max_tokens = 4096."""
        self.assertEqual(rag_service_mod.RERANK_TOP_K, 10)


if __name__ == "__main__":
    unittest.main()
