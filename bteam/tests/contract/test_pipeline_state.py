import time
from datetime import UTC, datetime, timedelta

import pytest
from oliview_core.db.lease import InMemoryLeaseStore

from pipelines.pipeline_runner import (
    LeaseBusyError,
    LeaseHeartbeatLostError,
    PipelineRunner,
    ResumeMismatchError,
    StepHandlerNotConfigured,
    failure_event,
)


def test_expired_lease_is_recovered_atomically():
    store = InMemoryLeaseStore(now=100.0)
    first = store.acquire("product_pipeline", "product:7", "owner-a", "run-a")
    assert first is True
    store.advance(61.0)
    recovered = store.acquire("product_pipeline", "product:7", "owner-b", "run-b")
    assert recovered is True
    assert store.history[-1]["error_code"] == "LEASE_EXPIRED"


def test_coordinator_blocks_another_cycle():
    store = InMemoryLeaseStore(now=100.0)
    assert store.acquire("cycle", "all", "owner-a", "run-a") is True
    assert store.acquire("cycle", "all", "owner-b", "run-b") is False


def test_all_products_uses_the_cycle_coordinator_lease():
    store = InMemoryLeaseStore(now=100.0)
    assert store.acquire("cycle", "all", "owner-a", "run-a") is True
    runner = PipelineRunner(lease_store=store)
    with pytest.raises(LeaseBusyError):
        runner.run_once(selector="all-products", steps="crawl")


def test_all_products_holds_each_product_lease_when_catalog_is_available():
    store = InMemoryLeaseStore(now=100.0)
    runner = PipelineRunner(
        lease_store=store,
        product_ids=lambda _context: [2, 7],
        step_handlers={"crawl": lambda _context: None},
    )

    runner.run_once(selector="all-products", steps="crawl")

    assert store.leases == {}
    assert store.acquire("product_pipeline", "product:2", "other", "other-run")
    assert store.acquire("product_pipeline", "product:7", "other", "other-run")


def test_all_products_rejects_a_busy_product_lease_before_running_steps():
    store = InMemoryLeaseStore(now=100.0)
    assert store.acquire("product_pipeline", "product:7", "other", "other-run")
    calls: list[str] = []
    runner = PipelineRunner(
        lease_store=store,
        product_ids=lambda _context: [2, 7],
        step_handlers={"crawl": lambda _context: calls.append("crawl")},
    )

    with pytest.raises(LeaseBusyError):
        runner.run_once(selector="all-products", steps="crawl")

    assert calls == []
    assert ("cycle", "all") not in store.leases


def test_runner_resumes_exact_run_without_replaying_completed_steps():
    calls = []
    failing = {"sentiment": True}

    def handler(context):
        calls.append(context.steps[0] if context.steps else "")
        if context.run_id and failing.pop("sentiment", False):
            raise RuntimeError("temporary")

    runner = PipelineRunner(step_handlers={"crawl": handler, "sentiment": handler})
    with pytest.raises(RuntimeError):
        runner.run_once(selector="product:7", steps="crawl,sentiment")
    run_id = next(iter(runner.runs))
    runner.run_once(selector="product:7", steps="crawl,sentiment", resume_run_id=run_id)
    assert len(calls) == 3
    with pytest.raises(ResumeMismatchError):
        runner.run_once(
            selector="product:8", steps="crawl,sentiment", resume_run_id=run_id
        )


def test_runner_uses_interval_to_create_an_immutable_cycle_watermark():
    observed = []
    runner = PipelineRunner(
        step_handlers={"crawl": lambda context: observed.append(context.cycle_watermark)}
    )
    before = datetime.now(UTC) - timedelta(hours=24)
    result = runner.run_once(selector="product:7", steps="crawl", interval_hours=24)
    after = datetime.now(UTC) - timedelta(hours=24)

    assert len(observed) == 1
    assert before <= observed[0] <= after
    assert result.cycle_watermark == observed[0]


def test_runner_rejects_active_product_lease():
    store = InMemoryLeaseStore(now=100)
    assert store.acquire("product_pipeline", "product:7", "other", "other-run")
    runner = PipelineRunner(lease_store=store)
    with pytest.raises(LeaseBusyError):
        runner.run_once(selector="product:7", steps="crawl")


def test_runner_does_not_mark_unconfigured_step_as_completed():
    runner = PipelineRunner()

    with pytest.raises(StepHandlerNotConfigured):
        runner.run_once(selector="product:7", steps="crawl")


def test_runner_heartbeats_lease_before_each_step():
    class RecordingLeaseStore(InMemoryLeaseStore):
        heartbeat_calls = 0

        def heartbeat(self, step_name, scope_key, owner_token):
            self.heartbeat_calls += 1
            return super().heartbeat(step_name, scope_key, owner_token)

    store = RecordingLeaseStore(now=100)
    runner = PipelineRunner(
        lease_store=store,
        step_handlers={step: lambda _context: None for step in ("crawl", "report")},
    )
    runner.run_once(selector="product:7", steps="crawl,report")
    assert store.heartbeat_calls == 2


def test_failure_event_is_structured_and_secret_free():
    event = failure_event(
        selector="product:7",
        steps="crawl",
        error=LeaseHeartbeatLostError("lease heartbeat lost"),
        run_id="run-1",
    )
    assert event == {
        "event": "pipeline_failed",
        "status": "FAILED",
        "selector": "product:7",
        "steps": "crawl",
        "run_id": "run-1",
        "error_code": "LeaseHeartbeatLostError",
        "message": "lease heartbeat lost",
    }


def test_runner_watchdog_heartbeats_during_long_handler_and_fails_closed():
    class FailingHeartbeatStore(InMemoryLeaseStore):
        heartbeat_calls = 0

        def heartbeat(self, step_name, scope_key, owner_token):
            self.heartbeat_calls += 1
            if self.heartbeat_calls > 1:
                return False
            return super().heartbeat(step_name, scope_key, owner_token)

    store = FailingHeartbeatStore(now=100, heartbeat_seconds=0.01, ttl_seconds=0.03)
    runner = PipelineRunner(
        lease_store=store,
        step_handlers={"crawl": lambda _context: time.sleep(0.05)},
    )

    with pytest.raises(LeaseHeartbeatLostError):
        runner.run_once(selector="product:7", steps="crawl")

    assert store.heartbeat_calls >= 2
    assert runner.runs[next(iter(runner.runs))].metadata["status"] == "FAILED"
