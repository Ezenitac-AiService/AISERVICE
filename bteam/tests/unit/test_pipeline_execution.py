from __future__ import annotations

from pipelines.execution import chunks, cycle_watermark, process_in_chunks


def test_pipeline_uses_fixed_500_row_chunks_and_advances_only_after_success():
    batches = list(chunks(list(range(1001))))
    assert [len(batch) for batch in batches] == [500, 500, 1]
    seen: list[int] = []
    assert (
        process_in_chunks(list(range(1001)), lambda batch: seen.append(len(batch)))
        == 1001
    )
    assert seen == [500, 500, 1]
    watermark = cycle_watermark("cycle-1")
    assert watermark.advanced is False
    assert watermark.advance().advanced is True
