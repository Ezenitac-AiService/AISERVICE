from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

CANONICAL_STEPS = ("crawl", "sentence_split", "sentiment", "report", "index")


@dataclass(frozen=True)
class ChangedInput:
    key: str
    changed_at: datetime


def select_changed_inputs(
    rows: Iterable[ChangedInput],
    *,
    checkpoint: datetime | None,
    cycle_watermark: datetime,
) -> tuple[ChangedInput, ...]:
    """Select only changes after the last success and before the cycle snapshot."""
    if cycle_watermark.tzinfo is None:
        raise ValueError("cycle watermark must be timezone-aware")
    if checkpoint is not None and checkpoint.tzinfo is None:
        raise ValueError("step checkpoint must be timezone-aware")
    return tuple(
        row
        for row in rows
        if row.changed_at.tzinfo is not None
        and row.changed_at <= cycle_watermark
        and (checkpoint is None or row.changed_at > checkpoint)
    )


def parse_steps(raw: str | Iterable[str]) -> tuple[str, ...]:
    values = (
        [part.strip() for part in raw.split(",")]
        if isinstance(raw, str)
        else [str(part).strip() for part in raw]
    )
    values = [value for value in values if value]
    if not values:
        raise ValueError("at least one pipeline step is required")
    if "all" in values:
        if len(values) != 1:
            raise ValueError("all is exclusive and cannot be combined with a step")
        return CANONICAL_STEPS
    unknown = sorted(set(values) - set(CANONICAL_STEPS))
    if unknown:
        raise ValueError(f"unknown pipeline step(s): {', '.join(unknown)}")
    if len(values) != len(set(values)):
        raise ValueError("duplicate pipeline step")
    return tuple(step for step in CANONICAL_STEPS if step in values)
