"""Contract tests for the 9-check verification suite (T085)."""

import json


def test_report_uses_exact_nine_ids_and_portal_subchecks(aiservice_root, contracts_dir):
    report = json.loads((aiservice_root / "migration_pack/verification_report.json").read_text(encoding="utf-8"))
    expected = [
        "portal", "ateam_pilos", "bteam_oliview", "bteam_chata", "bteam_chatb",
        "model_gateway_llm", "model_gateway_embedding", "model_gateway_rerank", "redis",
    ]
    assert [check["id"] for check in report["checks"]] == expected
    portal = report["checks"][0]
    assert {subcheck["id"] for subcheck in portal["subchecks"]} == {
        "portal_root", "portal_changelog", "portal_changelog_data", "portal_static_assets",
    }
    assert report["passed_checks"] + report["failed_checks"] == report["total_checks"] == 9
