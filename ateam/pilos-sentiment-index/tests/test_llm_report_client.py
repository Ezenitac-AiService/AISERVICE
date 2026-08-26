import json
import unittest

from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from openai import APIConnectionError, APIStatusError

from pilos.collection.ai_clients.llm_report_client import (
    REPORT_MAX_TOKENS,
    REPORT_TEMPERATURE,
    LlmCompletion,
    LlmReportClientSettings,
    LlmReportResponseError,
    LlmReportTransportError,
    OpenAICompatibleLlmReportClient,
    build_report_response_format,
    parse_market_commentary_response,
)
from pilos.dto.llm_report_dto import ReportGenerationResult
from tests.test_llm_report_analysis import make_request, valid_commentary


def make_settings():
    return LlmReportClientSettings(
        provider="academy",
        base_url="http://internal.example:8081/v1",
        api_key="EMPTY",
        model="qwen3.5-4b",
        output_mode="json_object",
        timeout_seconds=60.0,
    )


def make_completion(payload=None, *, finish_reason="stop"):
    if payload is None:
        payload = valid_commentary().model_dump(mode="json")
    return SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    content=json.dumps(payload, ensure_ascii=False),
                    refusal=None,
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=90),
    )


class OpenAICompatibleLlmReportClientTest(unittest.TestCase):
    @patch("pilos.collection.ai_clients.llm_report_client.OpenAI")
    def test_sdk_automatic_retry_is_disabled(self, openai_class):
        OpenAICompatibleLlmReportClient(settings=make_settings())
        self.assertEqual(openai_class.call_args.kwargs["max_retries"], 0)

    def test_success_returns_validated_result(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion()
        result = OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        ).generate_report(make_request())

        self.assertIsInstance(result, ReportGenerationResult)
        self.assertEqual(result.provider_response_id, "response-1")
        self.assertEqual(result.input_tokens, 120)
        arguments = sdk_client.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments["response_format"], {"type": "json_object"})
        self.assertEqual(arguments["max_tokens"], 1400)

    def test_quality_failure_is_regenerated_once_with_reason(self):
        invalid = valid_commentary().model_dump(mode="json")
        invalid["market_commentary"] = (
            "댓글 수급 신호는 84점으로 확인됐습니다. "
            "개인 매도세가 주가 하락을 주도하고 있습니다."
        )
        sdk_client = Mock()
        sdk_client.chat.completions.create.side_effect = [
            make_completion(invalid),
            make_completion(),
        ]
        result = OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        ).generate_report(make_request())

        self.assertEqual(result.commentary, valid_commentary())
        self.assertEqual(sdk_client.chat.completions.create.call_count, 2)
        second_messages = sdk_client.chat.completions.create.call_args.kwargs["messages"]
        self.assertIn("직접 인과", second_messages[-1]["content"])

    def test_second_quality_failure_is_not_disguised_as_success(self):
        invalid = valid_commentary().model_dump(mode="json")
        invalid["conclusion"] = (
            "댓글 수급 신호 84점은 상승 확률이 높다는 뜻입니다."
        )
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion(invalid)
        client = OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )
        with self.assertRaisesRegex(LlmReportResponseError, "2회 실패"):
            client.generate_report(make_request())
        self.assertEqual(sdk_client.chat.completions.create.call_count, 2)

    def test_connection_error_retries_with_one_and_two_second_delays(self):
        sdk_client = Mock()
        request = httpx.Request("POST", "http://internal.example")
        sdk_client.chat.completions.create.side_effect = [
            APIConnectionError(request=request),
            APIConnectionError(request=request),
            make_completion(),
        ]
        sleep = Mock()
        OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
            sleep=sleep,
        ).generate_report(make_request())
        self.assertEqual(sleep.call_args_list[0].args, (1.0,))
        self.assertEqual(sleep.call_args_list[1].args, (2.0,))

    def test_nonretryable_http_error_is_attempted_once(self):
        sdk_client = Mock()
        request = httpx.Request("POST", "http://internal.example")
        response = httpx.Response(400, request=request)
        sdk_client.chat.completions.create.side_effect = APIStatusError(
            "bad request",
            response=response,
            body=None,
        )
        with self.assertRaises(LlmReportTransportError):
            OpenAICompatibleLlmReportClient(
                settings=make_settings(),
                sdk_client=sdk_client,
            ).generate_report(make_request())
        self.assertEqual(sdk_client.chat.completions.create.call_count, 1)

    def test_provider_and_model_must_match(self):
        request = make_request(provider="groq")
        with self.assertRaisesRegex(ValueError, "provider·model"):
            OpenAICompatibleLlmReportClient(
                settings=make_settings(),
                sdk_client=Mock(),
            ).generate_report(request)


class ResponseContractTest(unittest.TestCase):
    def test_response_schema_has_only_two_fields(self):
        schema = build_report_response_format("json_schema")["json_schema"]
        properties = schema["schema"]["properties"]

        self.assertEqual(
            set(properties.keys()),
            {"market_commentary", "conclusion"},
        )

    def test_extra_evidence_fields_are_rejected(self):
        payload = valid_commentary().model_dump(mode="json")
        payload["key_expressions"] = ["매수"]

        with self.assertRaises(ValueError):
            parse_market_commentary_response(
                content=json.dumps(payload, ensure_ascii=False),
                finish_reason="stop",
            )


class ResponseParsingTest(unittest.TestCase):
    def test_json_response_is_parsed_without_recovery(self):
        result = parse_market_commentary_response(
            content=json.dumps(
                valid_commentary().model_dump(mode="json"),
                ensure_ascii=False,
            ),
            finish_reason="stop",
        )
        self.assertEqual(result, valid_commentary())

    def test_think_code_fence_and_nonstop_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "<think>"):
            parse_market_commentary_response(
                content="<think>내부</think>{}",
                finish_reason="stop",
            )
        with self.assertRaisesRegex(ValueError, "코드 펜스"):
            parse_market_commentary_response(
                content="```json\n{}\n```",
                finish_reason="stop",
            )
        with self.assertRaisesRegex(ValueError, "정상 종료"):
            parse_market_commentary_response(content="{}", finish_reason="length")

    def test_response_format_matches_mode(self):
        self.assertEqual(build_report_response_format("json_object"), {"type": "json_object"})
        self.assertIsNone(build_report_response_format("prompt_json"))
        strict = build_report_response_format("json_schema_strict")
        self.assertTrue(strict["json_schema"]["strict"])


if __name__ == "__main__":
    unittest.main()


class RequestCompletionBoundaryTest(unittest.TestCase):
    """
    production 생성과 프롬프트 실험이 공유하는 호출 경계를 고정한다.

    실험 노트북이 SDK 호출을 복제하지 않고 이 경계를 재사용한다.
    """

    def test_arbitrary_messages_return_raw_completion(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion()
        client = OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )
        messages = [
            {"role": "system", "content": "실험용 시스템 프롬프트"},
            {"role": "user", "content": "실험용 사용자 프롬프트"},
        ]

        completion = client.request_completion(messages)

        self.assertIsInstance(completion, LlmCompletion)
        self.assertEqual(completion.finish_reason, "stop")
        self.assertEqual(completion.response_id, "response-1")
        self.assertEqual(completion.input_tokens, 120)
        self.assertEqual(completion.output_tokens, 90)
        self.assertIsNone(completion.refusal)
        self.assertIn("market_commentary", completion.content)

    def test_generation_settings_match_production(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion()
        client = OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        client.request_completion([{"role": "user", "content": "확인"}])

        arguments = sdk_client.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments["temperature"], REPORT_TEMPERATURE)
        self.assertEqual(arguments["max_tokens"], REPORT_MAX_TOKENS)
        self.assertEqual(arguments["model"], "qwen3.5-4b")
        self.assertEqual(
            arguments["response_format"],
            {"type": "json_object"},
        )

    def test_generate_report_uses_the_same_boundary(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion()
        client = OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        with patch.object(
            client,
            "request_completion",
            wraps=client.request_completion,
        ) as boundary:
            client.generate_report(make_request())

        boundary.assert_called_once()

    def test_multiple_choices_are_rejected(self):
        completion = make_completion()
        completion.choices.append(completion.choices[0])
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = completion
        client = OpenAICompatibleLlmReportClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        with self.assertRaisesRegex(ValueError, "정확히 한 건"):
            client.request_completion([{"role": "user", "content": "확인"}])
