from __future__ import annotations

from oliview_core.db.orm import Base, PipelineRunHistoryORM
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipelines.persistence import SqlAlchemyRunStore


def test_pipeline_checkpoint_is_saved_in_same_session_transaction():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        store = SqlAlchemyRunStore(session)
        row = store.record_step(
            run_id="r1", step_name="crawl", scope_key="product:7", status="RUNNING"
        )
        store.complete(row, checkpoint={"last_success_id": 7, "checkpoint_version": 1})
        session.commit()
    with Session(engine) as session:
        saved = session.query(PipelineRunHistoryORM).one()
        assert saved.status == "COMPLETED"
        assert '"last_success_id": 7' in (saved.checkpoint_payload or "")
