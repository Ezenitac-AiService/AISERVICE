import json
import os
import unittest

from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError

from pilos.collection.ai_clients.llm_capability import (
    LlmCapabilitySettings,
    probe_report_output_mode,
    run_llm_capability_probes,
)
from pilos.dto.llm_report_dto import LlmMarketCommentary


VALID_COMMENTARY = {
    "market_commentary": (
        "개인투자자 수급은 매수 우위로 관측됐습니다. "
        "댓글 수급 신호는 과거 동일 방향 대비 높은 수준입니다."
    ),
    "conclusion": (
        "매수 우위 구간에서 오늘의 댓글 신호가 상대적으로 높게 나타났습니다."
    ),
}


def make_settings():
    return LlmCapabilitySettings(
        provider="academy",
        base_url="http://internal.example:8081/v1",
        api_key="EMPTY",
        model="qwen3.5-4b",
        timeout_seconds=60.0,
    )


def completion(payload=None):
    if payload is None:
        payload = VALID_COMMENTARY
    return SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=json.dumps(payload, ensure_ascii=False),
                    refusal=None,
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
    )


class LlmMarketCommentaryTest(unittest.TestCase):
    def test_valid_korean_commentary_is_accepted(self):
        value = LlmMarketCommentary.model_validate(VALID_COMMENTARY)
        self.assertIn("댓글 수급 신호", value.market_commentary)

    def test_removed_evidence_fields_are_rejected(self):
        invalid = {
            **VALID_COMMENTARY,
            "key_expressions": [],
            "used_comment_refs": [],
        }
        with self.assertRaises(ValidationError):
            LlmMarketCommentary.model_validate(invalid)

    def test_extra_field_is_rejected(self):
        invalid = {**VALID_COMMENTARY, "unexpected": "value"}
        with self.assertRaises(ValidationError):
            LlmMarketCommentary.model_validate(invalid)

    def test_non_korean_text_is_rejected(self):
        invalid = {**VALID_COMMENTARY, "conclusion": "english only text value"}
        with self.assertRaises(ValidationError):
            LlmMarketCommentary.model_validate(invalid)


class CapabilityProbeTest(unittest.TestCase):
    def test_json_object_probe_uses_market_commentary_contract(self):
        client = Mock()
        client.chat.completions.create.return_value = completion()
        result = probe_report_output_mode(
            client=client,
            settings=make_settings(),
            output_mode="json_object",
        )
        self.assertTrue(result.success)
        arguments = client.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments["response_format"], {"type": "json_object"})
        self.assertIn("market_commentary", arguments["messages"][1]["content"])

    def test_invalid_report_response_returns_neutral_failure(self):
        client = Mock()
        client.chat.completions.create.return_value = completion({"bad": "shape"})
        result = probe_report_output_mode(
            client=client,
            settings=make_settings(),
            output_mode="json_object",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "ValidationError")

    def test_all_capabilities_are_checked_without_fallback(self):
        client = Mock()
        client.models.list.return_value = SimpleNamespace(
            data=[SimpleNamespace(id="qwen3.5-4b")]
        )
        client.chat.completions.create.side_effect = [
            SimpleNamespace(
                id="basic-1",
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content="연결이 정상입니다."),
                    )
                ],
                usage=None,
            ),
            completion(),
            completion(),
            completion(),
            completion(),
        ]
        results = run_llm_capability_probes(
            settings=make_settings(),
            client=client,
        )
        self.assertEqual(len(results), 6)
        self.assertEqual(client.chat.completions.create.call_count, 5)


class CapabilitySettingsTest(unittest.TestCase):
    @patch("pilos.collection.ai_clients.llm_capability.load_dotenv", lambda *a, **k: None)
    @patch.dict(os.environ, {}, clear=True)
    def test_settings_require_all_values(self):
        with self.assertRaisesRegex(ValueError, "capability 필수"):
            LlmCapabilitySettings.from_env()


if __name__ == "__main__":
    unittest.main()
