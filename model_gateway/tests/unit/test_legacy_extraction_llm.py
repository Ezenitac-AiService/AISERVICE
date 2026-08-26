"""Unit tests for legacy extraction scripts (.legacy/ATEAM_ExtractionItem.py & .legacy/BTEAM_ExtractionItem.py) local LLM integration."""

import os
import sys
import unittest.mock as mock
import pytest
from openai import OpenAI

# Ensure repo root and .legacy dir are on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_DIR = os.path.join(REPO_ROOT, ".legacy")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if LEGACY_DIR not in sys.path:
    sys.path.insert(0, LEGACY_DIR)

from ATEAM_ExtractionItem import (
    get_local_llm_client,
    get_target_model_name,
    process_stock_comment_sentiment_extraction,
)
from BTEAM_ExtractionItem import (
    process_review_sentiment_extraction,
)



def test_get_local_llm_client_default(monkeypatch):
    """T002: Test local LLM client initialization defaults to http://10.0.0.41:8000/v1."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client, base_url = get_local_llm_client()
    assert isinstance(client, OpenAI)
    assert "10.0.0.41:8000" in base_url or "8000/v1" in base_url


def test_get_local_llm_client_env_override(monkeypatch):
    """T002: Test OPENAI_BASE_URL and VLLM_API_BASE environment variable overrides."""
    monkeypatch.setenv("VLLM_API_BASE", "http://192.168.0.100:8000/v1")
    client, base_url = get_local_llm_client()
    assert base_url == "http://192.168.0.100:8000/v1"

    monkeypatch.setenv("OPENAI_BASE_URL", "http://10.0.0.41:9000/v1")
    client, base_url = get_local_llm_client()
    assert base_url == "http://10.0.0.41:9000/v1"


def test_get_target_model_name_resolution(monkeypatch):
    """T012/T013: Test model name resolution priority (OPENAI_MODEL_NAME > MODEL_NAME > default)."""
    monkeypatch.delenv("OPENAI_MODEL_NAME", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("CURRENT_GROQ_MODEL", raising=False)
    assert get_target_model_name() == "qwen3.5-2b"

    monkeypatch.setenv("MODEL_NAME", "gemma4-4b")
    assert get_target_model_name() == "gemma4-4b"

    monkeypatch.setenv("OPENAI_MODEL_NAME", "qwen3.5-9b")
    assert get_target_model_name() == "qwen3.5-9b"


def test_ateam_extraction_mock_success():
    """T003/T004/T005: Test ATEAM extraction pipeline with mock local LLM response."""
    mock_response = mock.MagicMock()
    mock_choice = mock.MagicMock()
    mock_choice.message.content = """{
      "results": [
        {
          "speaker": "주식초보",
          "category": "실적/재무",
          "sentiment": "매수/긍정",
          "target": "삼전",
          "sentence": "오늘 개장하자마자 삼전 4분기 실적 발표 나온 거 보셨나요?",
          "refined_sentence": "[삼성전자] 4분기 실적 발표 확인하셨나요?"
        }
      ]
    }"""
    mock_response.choices = [mock_choice]

    sample_timeline = "주식초보 (14:00): 오늘 개장하자마자 삼전 4분기 실적 발표 나온 거 보셨나요?"

    with mock.patch("ATEAM_ExtractionItem.client.chat.completions.create", return_value=mock_response):
        results = process_stock_comment_sentiment_extraction(sample_timeline)
        assert len(results) >= 1
        assert results[0]["speaker"] == "주식초보"
        assert results[0]["target"] == "삼성전자"  # Normalized from 삼전


def test_ateam_extraction_connection_failure():
    """T006: Test ATEAM extraction graceful handling on connection error."""
    with mock.patch("ATEAM_ExtractionItem.client.chat.completions.create", side_effect=Exception("Connection refused")):
        results = process_stock_comment_sentiment_extraction("test sample")
        assert results == []


def test_bteam_extraction_mock_success():
    """T007/T008/T009: Test BTEAM extraction pipeline with mock local LLM response."""
    mock_response = mock.MagicMock()
    mock_choice = mock.MagicMock()
    mock_choice.message.content = """{
      "results": [
        {
          "category": "맛",
          "target": "봉골레 파스타",
          "sentence": "봉골레 파스타는 조개 맛이 시원하고 감칠맛이 좋았습니다.",
          "refined_sentence": "[봉골레 파스타] 조개 맛이 시원하고 감칠맛이 좋았습니다."
        }
      ]
    }"""
    mock_response.choices = [mock_choice]

    sample_review = "봉골레 파스타는 조개 맛이 시원하고 감칠맛이 좋았습니다."

    with mock.patch("BTEAM_ExtractionItem.client.chat.completions.create", return_value=mock_response):
        results = process_review_sentiment_extraction(sample_review)
        assert len(results) >= 1
        assert results[0]["category"] == "맛"
        assert results[0]["target"] == "봉골레 파스타"


def test_bteam_extraction_connection_failure():
    """T010: Test BTEAM extraction graceful handling on connection error."""
    with mock.patch("BTEAM_ExtractionItem.client.chat.completions.create", side_effect=Exception("Connection refused")):
        results = process_review_sentiment_extraction("test review")
        assert results == []



def test_multi_model_lineup_rotation_loop(monkeypatch):
    """T011: Test multi-model lineup rotation across gemma4-e2b, gemma4-e4b, qwen3.5-2b, qwen3.5-4b, qwen3.5-9b."""
    lineup = ["gemma4-e2b", "gemma4-e4b", "qwen3.5-2b", "qwen3.5-4b", "qwen3.5-9b"]
    for model in lineup:
        monkeypatch.setenv("OPENAI_MODEL_NAME", model)
        assert get_target_model_name() == model

