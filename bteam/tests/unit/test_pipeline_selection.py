import pytest

from pipelines.pipeline_runner import build_parser, resolve_selector
from pipelines.pipeline_selection import CANONICAL_STEPS, parse_steps


def test_steps_are_canonical_and_all_is_exclusive():
    assert parse_steps("sentiment,crawl") == ("crawl", "sentiment")
    assert parse_steps("all") == CANONICAL_STEPS
    with pytest.raises(ValueError):
        parse_steps("all,crawl")
    with pytest.raises(ValueError):
        parse_steps("crawl,crawl")


def test_product_code_is_a_mutually_exclusive_pipeline_selector():
    args = build_parser().parse_args(
        ["--product-code", "A000000189181", "--steps", "crawl"]
    )

    assert args.product_code == "A000000189181"
    assert resolve_selector(product_code=args.product_code) == (
        "product_code:A000000189181"
    )
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--product-id", "1", "--product-code", "A000000189181"]
        )


def test_product_code_lookup_rejects_unknown_code():
    with pytest.raises(ValueError, match="product code not found"):
        resolve_selector(product_code="missing", lookup=lambda _code: None)


from datetime import UTC, datetime, timedelta

from pipelines.pipeline_selection import ChangedInput, select_changed_inputs


def test_changed_inputs_are_bounded_by_checkpoint_and_cycle_watermark():
    cycle = datetime(2026, 8, 27, 12, tzinfo=UTC)
    rows = [
        ChangedInput("before", cycle - timedelta(seconds=1)),
        ChangedInput("in-window", cycle - timedelta(microseconds=1)),
        ChangedInput("after", cycle + timedelta(seconds=1)),
    ]

    selected = select_changed_inputs(
        rows,
        checkpoint=cycle - timedelta(seconds=2),
        cycle_watermark=cycle,
    )

    assert [row.key for row in selected] == ["before", "in-window"]
