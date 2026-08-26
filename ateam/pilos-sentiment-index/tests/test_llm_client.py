import os
import unittest

from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from openai import APIConnectionError, APIStatusError

from pilos.collection.ai_clients.llm_client import (
    ChatCompletionResult,
    LlmClientSettings,
    LlmResponseError,
    LlmTransportError,
    OpenAICompatibleLlmClient,
)


def make_settings() -> LlmClientSettings:
    return LlmClientSettings(
        provider="academy",
        base_url="http://internal.example:8081/v1",
        api_key="EMPTY",
        model="qwen3.5-4b",
        timeout_seconds=30.0,
    )


def make_completion(
    *,
    content: str | None = "연결이 정상입니다.",
    finish_reason: str | None = "stop",
):
    return SimpleNamespace(
        id="response-1",
        model="qwen3.5-4b",
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(
                    content=content,
                    refusal=None,
                ),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=8,
        ),
    )


class OpenAICompatibleLlmClientTest(unittest.TestCase):
    @patch("pilos.collection.ai_clients.llm_client.OpenAI")
    def test_sdk_automatic_retry_is_disabled(self, openai_class):
        OpenAICompatibleLlmClient(settings=make_settings())

        self.assertEqual(openai_class.call_args.kwargs["max_retries"], 0)

    def test_success_returns_provider_neutral_result(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion()
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        result = client.create_chat_completion(
            messages=[{"role": "user", "content": "안녕하세요."}],
            temperature=0.2,
            max_tokens=256,
        )

        self.assertIsInstance(result, ChatCompletionResult)
        self.assertEqual(result.content, "연결이 정상입니다.")
        self.assertEqual(result.provider_response_id, "response-1")
        self.assertEqual(result.input_tokens, 12)
        arguments = sdk_client.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments["model"], "qwen3.5-4b")
        self.assertEqual(arguments["temperature"], 0.2)
        self.assertEqual(arguments["max_tokens"], 256)
        self.assertNotIn("api_key", arguments)

    def test_connection_error_retries_with_expected_delays(self):
        sdk_client = Mock()
        request = httpx.Request("POST", "http://internal.example")
        sdk_client.chat.completions.create.side_effect = [
            APIConnectionError(request=request),
            APIConnectionError(request=request),
            make_completion(),
        ]
        sleep = Mock()
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
            sleep=sleep,
        )

        result = client.create_chat_completion(
            messages=[{"role": "user", "content": "연결 확인"}]
        )

        self.assertEqual(result.content, "연결이 정상입니다.")
        self.assertEqual(sdk_client.chat.completions.create.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [1.0, 2.0],
        )

    def test_skip_thinking_prefills_and_returns_only_final_answer(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion(
            content=(
                "<think>\n\n</think>\n\n"
                "PILOS 최종 답변입니다."
            )
        )
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        result = client.create_chat_completion(
            messages=[{"role": "user", "content": "질문"}],
            skip_thinking=True,
        )

        self.assertEqual(result.content, "PILOS 최종 답변입니다.")
        request_messages = (
            sdk_client.chat.completions.create.call_args.kwargs[
                "messages"
            ]
        )
        self.assertEqual(
            request_messages[-1],
            {
                "role": "assistant",
                "content": "<think>\n\n</think>\n\n",
            },
        )

    def test_skip_thinking_rejects_incomplete_reasoning(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion(
            content="<think>완료되지 않은 생각 과정",
            finish_reason="length",
        )
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        with self.assertRaises(LlmResponseError):
            client.create_chat_completion(
                messages=[{"role": "user", "content": "질문"}],
                skip_thinking=True,
            )

    def test_retryable_http_error_is_tried_three_times(self):
        sdk_client = Mock()
        request = httpx.Request("POST", "http://internal.example")
        response = httpx.Response(500, request=request)
        sdk_client.chat.completions.create.side_effect = APIStatusError(
            "server failed",
            response=response,
            body=None,
        )
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
            sleep=Mock(),
        )

        with self.assertRaisesRegex(LlmTransportError, "3회"):
            client.create_chat_completion(
                messages=[{"role": "user", "content": "연결 확인"}]
            )

        self.assertEqual(sdk_client.chat.completions.create.call_count, 3)

    def test_nonretryable_http_error_is_attempted_once(self):
        sdk_client = Mock()
        request = httpx.Request("POST", "http://internal.example")
        response = httpx.Response(400, request=request)
        sdk_client.chat.completions.create.side_effect = APIStatusError(
            "bad request",
            response=response,
            body=None,
        )
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        with self.assertRaisesRegex(LlmTransportError, "재시도하지"):
            client.create_chat_completion(
                messages=[{"role": "user", "content": "연결 확인"}]
            )

        sdk_client.chat.completions.create.assert_called_once()

    def test_invalid_response_is_not_retried(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = make_completion(
            content=""
        )
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        with self.assertRaises(LlmResponseError):
            client.create_chat_completion(
                messages=[{"role": "user", "content": "연결 확인"}]
            )

        sdk_client.chat.completions.create.assert_called_once()

    def test_empty_messages_are_rejected_before_call(self):
        sdk_client = Mock()
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        with self.assertRaisesRegex(ValueError, "한 건 이상"):
            client.create_chat_completion(messages=[])

        sdk_client.chat.completions.create.assert_not_called()

    def test_invalid_message_fields_are_rejected_before_call(self):
        sdk_client = Mock()
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        for messages in (
            [{"role": "", "content": "질문"}],
            [{"role": "user", "content": "   "}],
        ):
            with self.subTest(messages=messages):
                with self.assertRaises(ValueError):
                    client.create_chat_completion(messages=messages)

        sdk_client.chat.completions.create.assert_not_called()

    def test_invalid_generation_options_are_rejected_before_call(self):
        sdk_client = Mock()
        client = OpenAICompatibleLlmClient(
            settings=make_settings(),
            sdk_client=sdk_client,
        )

        with self.assertRaises(ValueError):
            client.create_chat_completion(
                messages=[{"role": "user", "content": "질문"}],
                temperature=2.1,
            )

        with self.assertRaises(ValueError):
            client.create_chat_completion(
                messages=[{"role": "user", "content": "질문"}],
                max_tokens=0,
            )

        sdk_client.chat.completions.create.assert_not_called()


class LlmClientSettingsTest(unittest.TestCase):
    def test_chat_settings_are_loaded_and_base_url_is_normalized(self):
        environment = {
            "LLM_PROVIDER": "academy",
            "LLM_BASE_URL": "http://internal.example:8081/v1/",
            "LLM_API_KEY": "EMPTY",
            "CHAT_LLM_MODEL": "qwen3.5-4b",
            "CHAT_LLM_TIMEOUT_SECONDS": "30",
        }

        with (
            patch.dict(os.environ, environment, clear=True),
            patch("pilos.collection.ai_clients.llm_client.load_dotenv"),
        ):
            settings = LlmClientSettings.from_env()

        self.assertEqual(settings.model, "qwen3.5-4b")
        self.assertEqual(settings.timeout_seconds, 30.0)
        self.assertEqual(
            settings.base_url,
            "http://internal.example:8081/v1",
        )

    def test_missing_settings_are_rejected(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("pilos.collection.ai_clients.llm_client.load_dotenv"),
        ):
            with self.assertRaisesRegex(ValueError, "필수 환경변수"):
                LlmClientSettings.from_env()


if __name__ == "__main__":
    unittest.main()
