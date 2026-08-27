from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import STATE_TRANSITIONS


@dataclass
class Checkpoint:
    step_name: str
    scope_key: str
    checkpoint_version: int
    last_success_id: int | str | None
    input_checksum: str
    output_count: int
    watermark: datetime


@dataclass
class PipelineRun:
    run_id: str
    selector: str
    steps: tuple[str, ...]
    status: str = "RUNNING"
    checkpoints: dict[tuple[str, str], Checkpoint] = field(default_factory=dict)
    error_code: str | None = None

    def transition(self, new_status: str, *, error_code: str | None = None) -> None:
        if new_status not in STATE_TRANSITIONS.get(self.status, frozenset()):
            raise ValueError(
                f"invalid pipeline state transition: {self.status} -> {new_status}"
            )
        self.status = new_status
        self.error_code = error_code

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        if checkpoint.step_name not in self.steps:
            raise ValueError("checkpoint step is not part of this run")
        self.checkpoints[(checkpoint.step_name, checkpoint.scope_key)] = checkpoint
