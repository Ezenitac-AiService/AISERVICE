from pathlib import Path

from deployment.monitor_soak import SoakMetric, evaluate_soak_metric

ROOT = Path(__file__).resolve().parents[2]


def test_soak_metric_healthy():
    metric = SoakMetric(
        timestamp="2026-08-28T14:00:00Z",
        http_5xx_count=0,
        http_probe_success_rate=1.0,
        p95_latency_seconds=1.2,
        consecutive_probe_failures=0,
        consecutive_sla_violations=0,
        pii_leakage_detected=False,
        hallucination_detected=False,
    )
    should_rollback, reason = evaluate_soak_metric(metric, run_mode="DEMO")
    assert should_rollback is False
    assert reason == "HEALTHY"


def test_soak_metric_5xx_trigger():
    metric = SoakMetric(
        timestamp="2026-08-28T14:00:00Z",
        http_5xx_count=1,
        http_probe_success_rate=0.75,
        p95_latency_seconds=1.2,
        consecutive_probe_failures=0,
        consecutive_sla_violations=0,
        pii_leakage_detected=False,
        hallucination_detected=False,
    )
    should_rollback, reason = evaluate_soak_metric(metric, run_mode="DEMO")
    assert should_rollback is True
    assert "5xx 에러" in reason


def test_soak_metric_consecutive_probe_failures_trigger():
    metric = SoakMetric(
        timestamp="2026-08-28T14:00:00Z",
        http_5xx_count=0,
        http_probe_success_rate=0.0,
        p95_latency_seconds=1.2,
        consecutive_probe_failures=2,
        consecutive_sla_violations=0,
        pii_leakage_detected=False,
        hallucination_detected=False,
    )
    should_rollback, reason = evaluate_soak_metric(metric, run_mode="DEMO")
    assert should_rollback is True
    assert "프로브 연속 실패" in reason


def test_soak_metric_sla_violation_trigger():
    metric = SoakMetric(
        timestamp="2026-08-28T14:00:00Z",
        http_5xx_count=0,
        http_probe_success_rate=1.0,
        p95_latency_seconds=22.5,  # DEMO max is 20.0s
        consecutive_probe_failures=0,
        consecutive_sla_violations=2,
        pii_leakage_detected=False,
        hallucination_detected=False,
    )
    should_rollback, reason = evaluate_soak_metric(metric, run_mode="DEMO")
    assert should_rollback is True
    assert "SLA 2회 연속 초과" in reason


def test_soak_metric_hallucination_trigger():
    metric = SoakMetric(
        timestamp="2026-08-28T14:00:00Z",
        http_5xx_count=0,
        http_probe_success_rate=1.0,
        p95_latency_seconds=1.5,
        consecutive_probe_failures=0,
        consecutive_sla_violations=0,
        pii_leakage_detected=False,
        hallucination_detected=True,
    )
    should_rollback, reason = evaluate_soak_metric(metric, run_mode="DEMO")
    assert should_rollback is True
    assert "환각/무인용 주장" in reason
