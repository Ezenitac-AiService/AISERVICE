"""Unit Tests for A-Team PILOS Gateway Client (Spec 037 US3)."""
import unittest
import sys
import os

# Add PILOS root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pilos.collection.ai_clients.llm_client import (
    LlmClientSettings,
    OpenAICompatibleLlmClient,
    ChatCompletionResult,
)


class MockSdkChoices:
    def __init__(self, content):
        self.message = type("Msg", (), {"content": content, "refusal": None})
        self.finish_reason = "stop"


class MockSdkCompletion:
    def __init__(self, content="테스트 리포트 결과입니다."):
        self.id = "chatcmpl_mock_001"
        self.model = "qwen3.5-4b"
        self.choices = [MockSdkChoices(content)]
        self.usage = type("Usage", (), {"prompt_tokens": 150, "completion_tokens": 50})


class MockSdkClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": self._create})()})
        self.last_arguments = None

    def _create(self, **kwargs):
        self.last_arguments = kwargs
        return MockSdkCompletion()


class TestPilosGatewayClient(unittest.TestCase):

    def test_pilos_client_top_p_parameter_injection(self):
        settings = LlmClientSettings(
            provider="openai",
            base_url="http://127.0.0.1:8081/v1",
            api_key="mock_key",
            model="qwen3.5-4b",
            timeout_seconds=120.0,
        )
        mock_sdk = MockSdkClient()
        client = OpenAICompatibleLlmClient(settings=settings, sdk_client=mock_sdk)

        result = client.create_chat_completion(
            messages=[{"role": "user", "content": "50건 뉴스 감성 분석을 수행하세요."}],
            temperature=0.3,
            top_p=0.85,
        )

        self.assertIsInstance(result, ChatCompletionResult)
        self.assertEqual(result.model, "qwen3.5-4b")
        # Top-P와 repetition_penalty가 정상 주입되었는지 검증
        self.assertEqual(mock_sdk.last_arguments.get("top_p"), 0.85)
        self.assertEqual(mock_sdk.last_arguments.get("temperature"), 0.3)
        self.assertEqual(mock_sdk.last_arguments.get("extra_body", {}).get("repetition_penalty"), 1.05)


if __name__ == "__main__":
    unittest.main()
