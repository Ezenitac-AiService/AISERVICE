from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

PHYSICAL_TABLE_MAP = {
    "Product": ("products", "brands", "product_categories", "categories"),
    "Review": ("reviews",),
    "ReviewSentence": ("review_aspect_sentences",),
    "SentimentAnalysis": ("aspect_sentiment_results",),
    "ProductReport": ("llm_product_reports", "llm_product_attribute_reports"),
    "ProductReportClaim": ("llm_product_report_claims",),
    "ProductReportCitation": ("llm_product_report_citations",),
    "PipelineRunHistory": ("pipeline_run_history",),
    "PipelineActiveLease": ("pipeline_active_lease",),
}

STATE_TRANSITIONS = {
    "RUNNING": frozenset({"COMPLETED", "FAILED"}),
    "FAILED": frozenset({"RUNNING"}),
    "COMPLETED": frozenset(),
}


@dataclass
class PipelineRunHistory:
    run_id: str
    step_name: str
    scope_key: str
    status: str = "RUNNING"
    error_code: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    history_unique: ClassVar[tuple[str, str, str]] = (
        "run_id",
        "step_name",
        "scope_key",
    )


@dataclass
class PipelineActiveLease:
    step_name: str
    scope_key: str
    owner_token: str
    run_id: str
    heartbeat_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    default_heartbeat_seconds: ClassVar[int] = 15
    default_ttl_seconds: ClassVar[int] = 60
    active_unique: ClassVar[tuple[str, str]] = ("step_name", "scope_key")


@dataclass
class ProductReportCitation:
    report_id: int | str
    claim_id: int | str
    source_review_id: int
    quote: str
    requires_same_product_review: ClassVar[bool] = True


@dataclass
class ProductReportClaim:
    claim_id: int | str
    report_id: int | str
    claim_type: str
    text: str
    citations: list[ProductReportCitation] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(UTC)
