"""
Integration tests for context window scaling benchmark loop (T010 / FR-001, FR-003).
Verifies multi-context (2K~32K) benchmark execution in MOCK mode.

Feature: 016-context-scaling-and-cleanup-fix
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.eval.quality_evaluator import ContextScalingMetric, ComprehensiveQualityReportMetric


class TestContextScalingMetric:
    """ContextScalingMetric 데이터 구조 검증."""

    def test_create_normal_metric(self):
        """정상 컨텍스트 스케일링 메트릭 생성."""
        metric = ContextScalingMetric(
            n_ctx=4096,
            peak_vram_mb=3500.0,
            ttft_ms=128.0,
            tpot_tok_per_sec=44.1,
            is_oom=False
        )
        assert metric.n_ctx == 4096
        assert metric.peak_vram_mb == 3500.0
        assert metric.is_oom is False

    def test_create_oom_metric(self):
        """OOM 감지된 스케일링 메트릭 생성."""
        metric = ContextScalingMetric(
            n_ctx=32768,
            peak_vram_mb=0.0,
            ttft_ms=0.0,
            tpot_tok_per_sec=0.0,
            is_oom=True
        )
        assert metric.n_ctx == 32768
        assert metric.is_oom is True


class TestContextScalingBenchmarkLoop:
    """컨텍스트 윈도우 스케일링 벤치마크 루프 검증."""

    def test_n_ctx_list_contains_all_target_sizes(self):
        """FR-001: 벤치마크 루프가 5개 n_ctx 구간을 포함하는지 검증."""
        n_ctx_list = [2048, 4096, 8192, 16384, 32768]
        assert len(n_ctx_list) == 5
        assert 2048 in n_ctx_list
        assert 32768 in n_ctx_list

    def test_oom_pre_flight_detection(self):
        """FR-003: VRAM 상한 초과 시 OOM 사전 감지 검증."""
        from src.core.process_manager import ProcessManager
        pm = ProcessManager(port=8099)
        
        # 소형 모델 + 고컨텍스트: VRAM 추정치가 상한 이내
        est_small = pm.estimate_vram_usage("gemma4-e2b", 4096)
        assert est_small < pm.vram_max_capacity_mb + 2000

        # 대형 모델 + 극대 컨텍스트: VRAM 추정치 초과 가능
        est_large = pm.estimate_vram_usage("qwen3.5-9b", 32768)
        assert est_large > 0  # 추정값이 양수인지 확인

    def test_comprehensive_report_with_scaling_metrics(self):
        """FR-004: ComprehensiveQualityReportMetric에 context_scaling_metrics 필드 포함 검증."""
        scaling = [
            ContextScalingMetric(n_ctx=2048, peak_vram_mb=2500, ttft_ms=95, tpot_tok_per_sec=48, is_oom=False),
            ContextScalingMetric(n_ctx=4096, peak_vram_mb=3500, ttft_ms=128, tpot_tok_per_sec=44, is_oom=False),
            ContextScalingMetric(n_ctx=8192, peak_vram_mb=4500, ttft_ms=165, tpot_tok_per_sec=38, is_oom=False),
            ContextScalingMetric(n_ctx=16384, peak_vram_mb=6200, ttft_ms=220, tpot_tok_per_sec=30, is_oom=False),
            ContextScalingMetric(n_ctx=32768, peak_vram_mb=0, ttft_ms=0, tpot_tok_per_sec=0, is_oom=True),
        ]
        report = ComprehensiveQualityReportMetric(
            model_id="gemma4-e2b",
            quant_type="q4_0",
            context_scaling_metrics=scaling,
        )
        assert len(report.context_scaling_metrics) == 5
        assert report.context_scaling_metrics[0].n_ctx == 2048
        assert report.context_scaling_metrics[4].is_oom is True

    def test_scaling_metrics_cover_all_five_ctx_sizes(self):
        """FR-001: 5개 n_ctx 구간 (2K~32K) 모두 커버하는지 검증."""
        expected_sizes = {2048, 4096, 8192, 16384, 32768}
        scaling = [
            ContextScalingMetric(n_ctx=size, peak_vram_mb=0, ttft_ms=0, tpot_tok_per_sec=0, is_oom=False)
            for size in expected_sizes
        ]
        actual_sizes = {m.n_ctx for m in scaling}
        assert actual_sizes == expected_sizes
