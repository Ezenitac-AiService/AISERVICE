import unittest
from unittest.mock import MagicMock, Mock

from pilos.collection.ai_clients.llm_client import (
    LlmClientSettings,
    OpenAICompatibleLlmClient,
)


class LlmClientStreamTest(unittest.TestCase):
    def setUp(self):
        self.settings = LlmClientSettings(
            provider="openai",
            base_url="http://test-server:8000/v1",
            api_key="EMPTY",
            model="test-model",
            timeout_seconds=120.0,
        )

    def test_stream_chat_completion_yields_tokens(self):
        mock_sdk_client = Mock()

        # Mock streaming chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "안녕"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = "하세요. "

        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta.content = "PILOS입니다."

        mock_sdk_client.chat.completions.create.return_value = [
            chunk1,
            chunk2,
            chunk3,
        ]

        client = OpenAICompatibleLlmClient(
            settings=self.settings,
            sdk_client=mock_sdk_client,
        )

        tokens = list(
            client.stream_chat_completion(
                messages=[{"role": "user", "content": "안녕하세요"}],
                max_tokens=256,
            )
        )

        self.assertEqual(tokens, ["안녕", "하세요. ", "PILOS입니다."])
        mock_sdk_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_sdk_client.chat.completions.create.call_args.kwargs
        self.assertTrue(call_kwargs.get("stream"))
        self.assertEqual(call_kwargs.get("max_tokens"), 256)


if __name__ == "__main__":
    unittest.main()
