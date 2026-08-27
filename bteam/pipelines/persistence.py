from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

from oliview_core.db.orm import PipelineRunHistoryORM
from sqlalchemy import select
from sqlalchemy.orm import Session


class SqlAlchemyRunStore:
    """Transaction boundary for immutable run/checkpoint rows."""

    def __init__(self, session: Session):
        self.session = session

    def record_step(
        self,
        *,
        run_id: str,
        step_name: str,
        scope_key: str,
        status: str,
        checkpoint: Mapping[str, object] | None = None,
        error_code: str | None = None,
    ) -> PipelineRunHistoryORM:
        row = self.session.scalar(
            select(PipelineRunHistoryORM).where(
                PipelineRunHistoryORM.run_id == run_id,
                PipelineRunHistoryORM.step_name == step_name,
                PipelineRunHistoryORM.scope_key == scope_key,
            )
        )
        if row is None:
            row = PipelineRunHistoryORM(
                run_id=run_id,
                step_name=step_name,
                scope_key=scope_key,
                started_at=datetime.now(UTC),
            )
            self.session.add(row)
        row.status = status
        row.checkpoint_payload = (
            json.dumps(checkpoint, ensure_ascii=False)
            if checkpoint is not None
            else None
        )
        row.error_code = error_code
        row.started_at = datetime.now(UTC)
        row.finished_at = None
        self.session.flush()
        self.session.commit()
        return row

    def complete(
        self, row: PipelineRunHistoryORM, *, checkpoint: Mapping[str, object]
    ) -> None:
        row.status = "COMPLETED"
        row.checkpoint_payload = json.dumps(checkpoint, ensure_ascii=False)
        row.finished_at = datetime.now(UTC)
        self.session.flush()
        self.session.commit()

    def fail(self, row: PipelineRunHistoryORM, *, error_code: str) -> None:
        row.status = "FAILED"
        row.error_code = error_code
        row.finished_at = datetime.now(UTC)
        self.session.flush()
        self.session.commit()

    def load_run(self, run_id: str) -> dict[str, object] | None:
        rows = self.session.scalars(
            select(PipelineRunHistoryORM)
            .where(PipelineRunHistoryORM.run_id == run_id)
            .order_by(PipelineRunHistoryORM.id)
        ).all()
        if not rows:
            return None
        checkpoints = [
            json.loads(row.checkpoint_payload) for row in rows if row.checkpoint_payload
        ]
        metadata = next((item for item in checkpoints if isinstance(item, dict)), {})
        step_checkpoints = {}
        for item in checkpoints:
            if isinstance(item, dict):
                raw_checkpoints = item.get("step_checkpoints", {})
                if isinstance(raw_checkpoints, dict):
                    step_checkpoints.update(raw_checkpoints)
        completed = {row.step_name for row in rows if row.status == "COMPLETED"}
        status = (
            "FAILED" if any(row.status == "FAILED" for row in rows) else "COMPLETED"
        )
        return {
            "selector": metadata.get("selector", ""),
            "steps": tuple(metadata.get("steps", ())),
            "cycle_watermark": metadata.get("cycle_watermark"),
            "completed": completed,
            "step_checkpoints": step_checkpoints,
            "status": status,
        }
