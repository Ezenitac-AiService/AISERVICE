"""
Integration tests for 3D Quality-Speed-VRAM Benchmark Runner and Report Generator.
"""

import os
import pytest
from unittest.mock import patch
from scripts.benchmark_quality import run_benchmark, generate_markdown_report


@patch("scripts.benchmark_quality.check_live_server", return_value=True)
@patch("scripts.benchmark_quality.request_live_inference", return_value={
    "content": '{"results": [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자 7만 원 돌파 기대"}]}',
    "tpot": 35.0,
    "ttft": 150.0,
    "elapsed_sec": 1.0
})
def test_run_benchmark_execution(mock_req, mock_live):
    """Verify that run_benchmark computes metrics for all 6 models when server is live."""
    reports, gpu_metadata = run_benchmark()
    assert len(reports) >= 6
    model_ids = [r.model_id for r in reports]
    assert "Qwen 3.5 2B" in model_ids
    assert "Qwen 3.5 4B" in model_ids
    assert "Qwen 3.5 9B" in model_ids
    assert "Gemma 4 E2B" in model_ids
    assert "Gemma 4 E4B" in model_ids
    assert "Gemma 4 12B" in model_ids

    for r in reports:
        assert 1.0 <= r.avg_quality_score <= 5.0
        assert r.quality_per_speed_index > 0.0
        assert r.quality_per_vram_index > 0.0


@patch("scripts.benchmark_quality.check_live_server", return_value=True)
@patch("scripts.benchmark_quality.request_live_inference", return_value={
    "content": '{"results": [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자 7만 원 돌파 기대"}]}',
    "tpot": 35.0,
    "ttft": 150.0,
    "elapsed_sec": 1.0
})
def test_markdown_report_generation(mock_req, mock_live, tmp_path):
    """Verify markdown report file generation and content structure."""
    reports, gpu_metadata = run_benchmark()
    test_report_path = os.path.join(tmp_path, "analysis_report_quality.md")
    
    generate_markdown_report(reports, test_report_path, gpu_metadata=gpu_metadata)
    assert os.path.exists(test_report_path)

    with open(test_report_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# Qwen 3.5 vs Gemma 4 3차원 종합 품질-속도-VRAM 교차 비교 분석 보고서" in content
    assert "Quality/Speed Index" in content
    assert "Quality/VRAM Index" in content
    assert "Qwen 3.5 4B" in content
    assert "Gemma 4 12B" in content


def test_vram_coloading_validation():
    """T018/FR-005/SC-004: Test VRAM co-loading validation across target GPU profiles."""
    from scripts.benchmark_quality import validate_vram_coloading_across_platforms
    coload_results = validate_vram_coloading_across_platforms()

    assert "legacy-i7-930-gtx1070" in coload_results
    assert "pascal-avx2-gtx1080ti" in coload_results
    assert "dev-rtx3060" in coload_results

    for profile_id, res in coload_results.items():
        assert res["passed"] is True
        assert len(res["fit_models"]) > 0


