from oliview_core.db.models import (
    PipelineActiveLease,
    PipelineRunHistory,
    ProductReportCitation,
)


def test_pipeline_constraints_and_citation_contract_are_declared():
    assert PipelineRunHistory.history_unique == ("run_id", "step_name", "scope_key")
    assert PipelineActiveLease.active_unique == ("step_name", "scope_key")
    assert PipelineActiveLease.default_heartbeat_seconds == 15
    assert PipelineActiveLease.default_ttl_seconds == 60
    assert ProductReportCitation.requires_same_product_review is True
