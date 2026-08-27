from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class StepResult:
    step_name: str
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    finished_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] | None = None
