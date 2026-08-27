from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class CycleWatermark:
    cycle_id: str
    started_at: datetime
    advanced: bool = False

    def advance(self) -> CycleWatermark:
        return CycleWatermark(self.cycle_id, self.started_at, True)


def chunks[T](rows: Sequence[T], *, size: int = 500) -> Iterable[Sequence[T]]:
    if size != 500:
        raise ValueError("Green database chunks are fixed at 500")
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def process_in_chunks[T](
    rows: Sequence[T], process: Callable[[Sequence[T]], None]
) -> int:
    processed = 0
    for batch in chunks(rows):
        process(batch)
        processed += len(batch)
    return processed


def cycle_watermark(cycle_id: str) -> CycleWatermark:
    return CycleWatermark(cycle_id, datetime.now(UTC))
