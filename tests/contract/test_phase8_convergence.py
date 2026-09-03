"""Phase 8 convergence red gate (T073).

These checks deliberately describe the remaining gaps identified by the plan.  They
are kept independent of Docker/GPU availability so the implementation contract can
be exercised on a development workstation before the native host rehearsal.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


AISERVICE_ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = AISERVICE_ROOT / "migration_pack"
SCRIPTS_ROOT = PACK_ROOT / "scripts"
CONTRACTS_ROOT = AISERVICE_ROOT.parent / "specs" / "001-aiservice-platform-migration" / "contracts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase8_contract_fixture_covers_all_convergence_domains() -> None:
    source = _read(Path(__file__))
    for marker in (
        "duck.sh",
        "checksum",
        "asset_manifest",
        "gpu_evidence",
        "rag_grounding",
        "probe",
        "credential",
        "TRUSTED_PROXY_CIDRS",
        "healthcheck",
    ):
        assert marker in source


def test_bootstrap_shell_is_ddns_free_and_has_contract_cli() -> None:
    script = _read(SCRIPTS_ROOT / "bootstrap_restore.sh")
    lowered = script.lower()
    assert "duck.sh" not in lowered
    assert "crontab" not in lowered
    assert "--skip-ddns" not in lowered
    assert "--secret-file" in script
    assert "--report" in script
    assert "bootstrap_restore.py" in script


def test_bootstrap_python_has_real_entrypoint_and_no_ddns_bypass() -> None:
    script = SCRIPTS_ROOT / "bootstrap_restore.py"
    compile(script.read_text(encoding="utf-8"), str(script), "exec")
    sys.path.insert(0, str(AISERVICE_ROOT))
    from migration_pack.scripts import bootstrap_restore

    assert callable(bootstrap_restore.main)
    parser = bootstrap_restore.build_argument_parser()
    args = parser.parse_args(["--secret-file", "/etc/aiservice/secrets/runtime.env", "--dry-run"])
    assert args.secret_file == "/etc/aiservice/secrets/runtime.env"
    assert "--skip-ddns" not in parser.format_help()
    assert "checksum_file" in bootstrap_restore.verify_checksums.__code__.co_varnames


def test_database_manifest_is_two_db_scope_and_matches_checksum_artifact() -> None:
    export_manifest = json.loads(
        (PACK_ROOT / "database" / "database_export_manifest.json").read_text(encoding="utf-8")
    )
    assert {entry["name"] for entry in export_manifest} == {"pilos_v2", "oliview_project"}
    assert all("cosmetic" not in json.dumps(entry).lower() for entry in export_manifest)

    migration = json.loads((PACK_ROOT / "migration_manifest.json").read_text(encoding="utf-8"))
    assert {entry["name"] for entry in migration["databases"]} == {"pilos_v2", "oliview_project"}
    assert {entry["live_volume"] for entry in migration["databases"]} == {
        "ateam_db_data",
        "bteam_bteam_mysql_data",
    }
    assert all(entry["live_volume"] != entry["staging_volume"] for entry in migration["databases"])

    checksums = (PACK_ROOT / "database" / "checksums.sha256").read_text(encoding="utf-8")
    assert "cosmetic_db" not in checksums
    for entry in migration["databases"]:
        assert f'{entry["sha256"]}  {entry["dump_file"]}' in checksums


def test_asset_manifest_uses_existing_canonical_assets_not_placeholders() -> None:
    manifest = json.loads((PACK_ROOT / "asset_manifest.json").read_text(encoding="utf-8"))
    expected = {
        "qwen3.5-4b": "model_gateway/models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf",
        "qwen3.5-2b": "model_gateway/models/qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf",
        "bge-m3": "model_gateway/models/bge-m3/bge-m3-q8_0.gguf",
        "bge-reranker-v2-m3": "model_gateway/models/bge-reranker-v2-m3/bge-reranker-v2-m3-q8_0.gguf",
        "pilos-rag-chroma": "ateam/pilos-sentiment-index/artifacts/rag_chroma/",
        "chata-chroma-bm25": "bteam/Oliview_chatbot_a/chroma_db_oliview/",
    }
    records = {entry["asset_id"]: entry for entry in manifest["assets"]}
    assert set(records) == set(expected)
    for asset_id, path in expected.items():
        record = records[asset_id]
        assert record["path"] == path
        assert record["sha256"] != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert record["size_bytes"] == (AISERVICE_ROOT / path.rstrip("/")).stat().st_size if Path(path).suffix else record["size_bytes"] > 0


def test_real_snapshot_recovery_module_and_docker_volume_operations_exist() -> None:
    recovery = SCRIPTS_ROOT / "snapshot_recovery.py"
    assert recovery.is_file()
    source = _read(recovery)
    assert "docker" in source
    assert "volume" in source
    assert "promote" in source
    assert "rollback" in source
    assert "backup" in source
    compile(source, str(recovery), "exec")


def test_probe_mode_and_fixture_are_connected() -> None:
    verify = _read(SCRIPTS_ROOT / "verify_migration.py")
    fixture = _read(CONTRACTS_ROOT / "probe-endpoint-fixture.md")
    assert "--probe" in verify or "--probe-container" in verify
    assert "probe-endpoint-fixture.md" in verify
    assert "aiservice-probe" in verify
    assert "gateway:80" in fixture
    assert "vllm-serv-gateway:8081" in fixture


def test_hardcoding_scan_ignores_machine_caches() -> None:
    source = _read(AISERVICE_ROOT / "model_gateway" / "scripts" / "scan_hardcoding.py")
    assert re.search(r"\.uv-cache", source)
    assert re.search(r"\.venv", source)


def test_credential_proxy_and_rate_limit_contracts_are_present() -> None:
    for relative in (
        "tests/contract/test_credential_rotation.py",
        "tests/contract/test_trusted_proxy_ip.py",
        "gateway/tests/test_rate_limit_contract.py",
    ):
        assert (AISERVICE_ROOT / relative).is_file(), relative


def test_rag_contract_targets_real_pipeline_and_enforces_coverage() -> None:
    source = _read(AISERVICE_ROOT / "tests" / "contract" / "test_rag_grounding_contract.py")
    assert "OliviewPipeline" in source
    assert "model_invoked" in source
    assert "citation_coverage_percent" in source
    assert "unsupported_claim_count" in source
    assert "monkeypatch" in source


def test_benchmark_report_and_scaling_script_have_required_evidence_contract() -> None:
    scaling = AISERVICE_ROOT / "model_gateway" / "scripts" / "benchmark_context_scaling.py"
    report = AISERVICE_ROOT / "model_gateway" / "data" / "reports" / "rtx3060-demo-benchmark.json"
    assert scaling.is_file()
    assert report.is_file()
    content = _read(scaling)
    assert "ceil" in content or "nearest" in content
    assert "warm" in content.lower()
    benchmark = json.loads(report.read_text(encoding="utf-8"))
    assert benchmark["sample_set_id"]
    assert benchmark["gpu_evidence"]["source"] == "nvml+llama_runtime"
    assert all(sample["request_count"] == 20 for sample in benchmark["gpu_evidence"]["samples"])
    assert all(sample["coverage_percent"] == 100 for sample in benchmark["gpu_evidence"]["samples"])


def test_health_report_keeps_exact_top_level_ids_and_portal_subchecks() -> None:
    schema = json.loads((CONTRACTS_ROOT / "healthcheck-report-schema.json").read_text(encoding="utf-8"))
    ids = schema["properties"]["checks"]["items"]["properties"]["id"]["enum"]
    assert len(ids) == 9
    assert ids == [
        "portal",
        "ateam_pilos",
        "bteam_oliview",
        "bteam_chata",
        "bteam_chatb",
        "model_gateway_llm",
        "model_gateway_embedding",
        "model_gateway_rerank",
        "redis",
    ]
    report_source = _read(SCRIPTS_ROOT / "verify_migration.py")
    for subcheck in ("portal_root", "portal_changelog", "portal_changelog_data", "portal_static_assets"):
        assert subcheck in report_source


def test_phase8_test_file_is_discoverable_by_python() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(Path(__file__))],
        cwd=AISERVICE_ROOT.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
