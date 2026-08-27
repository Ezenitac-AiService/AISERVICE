from datetime import UTC, datetime, timedelta

import pytest
from oliview_core.db.lease import SqlAlchemyLeaseStore
from oliview_core.db.orm import Base, PipelineActiveLeaseORM, PipelineRunHistoryORM
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pipelines.persistence import SqlAlchemyRunStore
from pipelines.pipeline_runner import PipelineRunner


def test_pipeline_persists_failed_step_and_resumes_in_new_runner():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    calls: list[str] = []

    with Session(engine) as session:

        def failing_handler(context):
            calls.append("sentiment")
            raise RuntimeError("temporary gateway failure")

        runner = PipelineRunner(
            step_handlers={
                "crawl": lambda _context: None,
                "sentence_split": lambda _context: None,
                "sentiment": failing_handler,
            },
            run_store=SqlAlchemyRunStore(session),
        )
        with pytest.raises(RuntimeError):
            runner.run_once(selector="product:2", steps="all")
        run_id = next(iter(runner.runs))
        failed_rows = session.scalars(
            select(PipelineRunHistoryORM).where(
                PipelineRunHistoryORM.run_id == run_id,
                PipelineRunHistoryORM.status == "FAILED",
            )
        ).all()
        assert [row.step_name for row in failed_rows] == ["sentiment"]

        resumed = PipelineRunner(
            step_handlers={
                step: lambda _context, step=step: calls.append(step)
                for step in ("crawl", "sentence_split", "sentiment", "report", "index")
            },
            run_store=SqlAlchemyRunStore(session),
        )
        result = resumed.run_once(
            selector="product:2", steps="all", resume_run_id=run_id
        )

        assert result.metadata["status"] == "COMPLETED"
        assert result.completed == {
            "crawl",
            "sentence_split",
            "sentiment",
            "report",
            "index",
        }
        rows = session.scalars(
            select(PipelineRunHistoryORM).where(PipelineRunHistoryORM.run_id == run_id)
        ).all()
        assert len(rows) == 5
        assert all(row.status == "COMPLETED" for row in rows)
        assert calls == ["sentiment", "sentiment", "report", "index"]


def test_sqlalchemy_lease_recovers_expired_owner_and_records_history():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = SqlAlchemyLeaseStore(session, ttl_seconds=60)
        assert first.acquire("product_pipeline", "product:2", "owner-a", "run-a")
        lease = session.get(
            PipelineActiveLeaseORM,
            {"step_name": "product_pipeline", "scope_key": "product:2"},
        )
        assert lease is not None
        lease.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        second = SqlAlchemyLeaseStore(session, ttl_seconds=60)
        assert second.acquire("product_pipeline", "product:2", "owner-b", "run-b")
        expired = session.scalars(
            select(PipelineRunHistoryORM).where(PipelineRunHistoryORM.run_id == "run-a")
        ).all()

    assert len(expired) == 1
    assert expired[0].status == "FAILED"
    assert expired[0].error_code == "LEASE_EXPIRED"


def test_all_products_cycle_watermark_and_exact_resume():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    executed_steps: list[tuple[str, str]] = []

    with Session(engine) as session:
        # 1. Run that fails on 'report'
        def step_tracker(step_name: str, fail: bool = False):
            def handler(context):
                executed_steps.append((step_name, context.selector))
                if fail:
                    raise RuntimeError(f"failure in {step_name}")

            return handler

        runner = PipelineRunner(
            step_handlers={
                "crawl": step_tracker("crawl"),
                "sentence_split": step_tracker("sentence_split"),
                "sentiment": step_tracker("sentiment"),
                "report": step_tracker("report", fail=True),
                "index": step_tracker("index"),
            },
            lease_store=SqlAlchemyLeaseStore(session, ttl_seconds=60),
            run_store=SqlAlchemyRunStore(session),
        )

        with pytest.raises(RuntimeError, match="failure in report"):
            runner.run_once(selector="all-products", steps="all", interval_hours=0)

        run_id = next(iter(runner.runs))
        persisted = session.scalars(
            select(PipelineRunHistoryORM)
            .where(PipelineRunHistoryORM.run_id == run_id)
            .order_by(PipelineRunHistoryORM.id)
        ).all()
        assert [r.step_name for r in persisted] == [
            "crawl",
            "sentence_split",
            "sentiment",
            "report",
        ]
        assert [r.status for r in persisted] == [
            "COMPLETED",
            "COMPLETED",
            "COMPLETED",
            "FAILED",
        ]

        # 2. Resumed runner picks up from 'report'
        resumed_runner = PipelineRunner(
            step_handlers={
                "crawl": step_tracker("crawl"),
                "sentence_split": step_tracker("sentence_split"),
                "sentiment": step_tracker("sentiment"),
                "report": step_tracker("report", fail=False),
                "index": step_tracker("index"),
            },
            lease_store=SqlAlchemyLeaseStore(session, ttl_seconds=60),
            run_store=SqlAlchemyRunStore(session),
        )

        resumed_result = resumed_runner.run_once(
            selector="all-products", steps="all", resume_run_id=run_id
        )

        assert resumed_result.metadata["status"] == "COMPLETED"
        assert resumed_result.completed == {
            "crawl",
            "sentence_split",
            "sentiment",
            "report",
            "index",
        }

        all_rows = session.scalars(
            select(PipelineRunHistoryORM)
            .where(PipelineRunHistoryORM.run_id == run_id)
            .order_by(PipelineRunHistoryORM.id)
        ).all()
        assert len(all_rows) == 5
        assert all(r.status == "COMPLETED" for r in all_rows)

