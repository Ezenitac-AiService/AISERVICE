"""
Unit tests for QualityEvaluator engine and weighted scoring formula.
"""

import os
import pytest
from src.eval.quality_evaluator import QualityEvaluator, QualityBenchmarkPrompt, QualityEvaluationMetric


@pytest.fixture
def evaluator():
    return QualityEvaluator()


def test_golden_dataset_loading(evaluator):
    """Verify that golden_dataset.json is loaded correctly with prompt entities."""
    assert len(evaluator.prompts) >= 2
    prompt_ids = [p.prompt_id for p in evaluator.prompts]
    assert "ATEAM-STOCK-01" in prompt_ids
    assert "BTEAM-REVIEW-01" in prompt_ids


def test_valid_json_response_evaluation(evaluator):
    """Verify quality score calculation for a valid structured JSON response."""
    valid_response = """
    {
      "results": [
        {
          "speaker": "A",
          "target": "삼성전자",
          "sentiment": "positive",
          "category": "투자가치",
          "refined_sentence": "A가 삼성전자 7만 원 돌파 기대"
        },
        {
          "speaker": "B",
          "target": "삼성전자",
          "sentiment": "negative",
          "category": "실적예상",
          "refined_sentence": "B가 삼성전자 실적 우려"
        },
        {
          "speaker": "C",
          "target": "SK하이닉스",
          "sentiment": "neutral",
          "category": "전망문의",
          "refined_sentence": "C가 SK하이닉스 주가 질문"
        },
        {
          "speaker": "B",
          "target": "SK하이닉스",
          "sentiment": "positive",
          "category": "업황수혜",
          "refined_sentence": "B가 SK하이닉스 상승 판단"
        }
      ]
    }
    """
    metric = evaluator.evaluate_response("ATEAM-STOCK-01", "qwen3.5-4b", valid_response)
    assert metric.json_schema_score == 1.0
    assert metric.slot_precision_score == 1.0
    assert metric.quantitative_score == 5.0
    assert metric.final_quality_score >= 4.5
    assert len(metric.error_flags) == 0


def test_invalid_json_response_handling(evaluator):
    """Verify invalid JSON response triggers INVALID_JSON flag and deduction."""
    invalid_response = "Broken JSON response: { 'results': [ missing quote ] }"
    metric = evaluator.evaluate_response("BTEAM-REVIEW-01", "gemma4-e4b", invalid_response)
    assert metric.json_schema_score == 0.0
    assert "INVALID_JSON" in metric.error_flags
    assert metric.final_quality_score < 4.0


def test_empty_response_handling(evaluator):
    """Verify empty response triggers EMPTY_RESPONSE flag and minimum score."""
    metric = evaluator.evaluate_response("ATEAM-STOCK-01", "qwen3.5-2b", "   ")
    assert metric.json_schema_score == 0.0
    assert metric.slot_precision_score == 0.0
    assert metric.final_quality_score == 1.0
    assert "EMPTY_RESPONSE" in metric.error_flags


def test_hallucination_flag_detection(evaluator):
    """Verify hallucination detection logic triggers flag and qualitative penalty."""
    hallucinatory_response = "This is a false_fact_confirmed hallucination trigger output."
    metric = evaluator.evaluate_response("ATEAM-STOCK-01", "gemma4-12b", hallucinatory_response)
    assert "HALLUCINATION" in metric.error_flags
    assert metric.narrative_naturalness_score < 4.0
