from __future__ import annotations

from pipelines.pipeline_runner import PipelineRunner


def test_green_pipeline_runs_canonical_steps_once():
    seen: list[str] = []
    runner = PipelineRunner(
        step_handlers={
            step: (lambda context, name=step: seen.append(name))
            for step in ("crawl", "sentence_split", "sentiment", "report", "index")
        }
    )
    result = runner.run_once(selector="all-products", steps="all")
    assert result.completed == {
        "crawl",
        "sentence_split",
        "sentiment",
        "report",
        "index",
    }
    assert seen == ["crawl", "sentence_split", "sentiment", "report", "index"]
    assert result.metadata["status"] == "COMPLETED"
