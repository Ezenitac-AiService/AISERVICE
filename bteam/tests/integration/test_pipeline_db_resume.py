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
