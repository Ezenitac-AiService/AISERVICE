"""T038--T050 수렴 작업의 회귀/계약 테스트."""

from __future__ import annotations

import gzip
import io
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

from make_migration_pack import build_argument_parser, build_manifest_inputs
from migration_pack.scripts.bootstrap_restore import (
    get_restore_targets,
    restore_database_dump,
)
from migration_pack.scripts.env_utils import load_environment, mask_secret
from migration_pack.scripts.export_docker_volumes import get_managed_volumes_map
from migration_pack.scripts.verify_migration import ENDPOINTS, build_verification_report
from model_gateway.scripts.probe_hardware import generate_build_profile


def test_environment_loader_merges_ddns_file_without_exposing_secret(tmp_path: Path):
    (tmp_path / ".env").write_text(
        "PILOS_DB_USER=from-root\nPILOS_DB_PASSWORD=from-root-secret\nDUCKDNS_DOMAIN=root-domain\n",
        encoding="utf-8",
    )
    ddns_dir = tmp_path / "ddns"
    ddns_dir.mkdir()
    (ddns_dir / ".env").write_text(
        "domain=ddns-domain\ntoken=ddns-secret\n", encoding="utf-8"
    )

    env = load_environment(tmp_path)

    assert env["PILOS_DB_USER"] == "from-root"
    assert env["DUCKDNS_DOMAIN"] == "root-domain"
    assert env["DUCKDNS_TOKEN"] == "ddns-secret"
    assert mask_secret("ddns-secret") != "ddns-secret"
    assert mask_secret("") == "<unset>"


def test_migration_cli_parser_honors_all_contract_options():
    parser = build_argument_parser()
    args = parser.parse_args(
        [
            "--include-models",
            "--force",
            "--dry-run",
            "--target-os",
            "ubuntu",
            "--target-cpu",
            "i7-930",
            "--target-gpu",
            "sm_61",
        ]
    )

    assert args.include_models is True
    assert args.force is True
    assert args.dry_run is True
    assert args.target_gpu == "sm_61"


def test_manifest_inputs_mask_duckdns_token_and_use_measured_values():
    inputs = build_manifest_inputs(
        project_root=Path("."),
        databases=[{"name": "pilos_v2", "row_count": 123}],
        volumes=[],
        target_cpu="i7-930",
        target_gpu="sm_61",
        environment={"DUCKDNS_DOMAIN": "example", "DUCKDNS_TOKEN": "secret-token"},
    )

    assert inputs["ddns_config"]["domain"] == "example"
    assert inputs["ddns_config"]["token"] != "secret-token"
    assert inputs["databases"][0]["row_count"] == 123


def test_managed_volumes_match_canonical_restore_set():
    assert set(get_managed_volumes_map()) == {
        "ateam_db_data",
        "bteam_bteam_mysql_data",
        "green_mysql_data",
        "green_chroma_data",
        "aiservice_redis_data",
    }


def test_restore_targets_are_environment_driven(tmp_path: Path):
    (tmp_path / ".env").write_text(
        "PILOS_DB_CONTAINER=pilos-custom\n"
        "PILOS_DB_NAME=custom_pilos\n"
        "PILOS_DB_USER=custom_user\n"
        "PILOS_DB_ROOT_PASSWORD=root-secret\n"
        "PILOS_DB_PASSWORD=db-secret\n"
        "BTEAM_DB_CONTAINER=bteam-custom\n"
        "BTEAM_DB_NAME=custom_olive\n"
        "BTEAM_DB_USER=olive-user\n"
        "BTEAM_DB_ROOT_PASSWORD=olive-root\n"
        "BTEAM_DB_PASSWORD=olive-secret\n",
        encoding="utf-8",
    )

    targets = get_restore_targets(tmp_path)

    assert targets[0]["container"] == "pilos-custom"
    assert targets[0]["db_name"] == "custom_pilos"
    assert targets[1]["password"] == "olive-secret"


def test_restore_database_dump_fails_on_any_nonzero_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    dump_path = tmp_path / "dump.sql.gz"
    with gzip.open(dump_path, "wb") as stream:
        stream.write(b"SELECT 1;\n")

    class FakeProcess:
        returncode = 7
        stdin = io.BytesIO()

        def wait(self):
            return self.returncode

        def communicate(self):
            return b"", b"warning without ERROR"

        @property
        def stderr(self):
            return io.BytesIO(b"warning without ERROR")

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    assert restore_database_dump("db", "schema", "user", "secret", dump_path) is False


def test_hardware_profile_uses_exact_budget_and_declares_fallbacks():
    profile = generate_build_profile(
        {
            "model_name": "Intel Core i7-930",
            "arch": "x86_64",
            "sse4_2": True,
            "avx": False,
            "avx2": False,
            "avx512": False,
            "is_nehalem_legacy": True,
        },
        {
            "present": True,
            "name": "NVIDIA GeForce GTX 1070",
            "compute_capability": "6.1",
            "compute_cap_int": 61,
            "vram_total_mb": 8192,
            "cuda_available": True,
        },
    )

    assert profile["vram_safety_limit_mb"] == 5000
    assert profile["runtime_fallback_chain"] == [
        "vllm",
        "llama.cpp-cuda",
        "llama.cpp-cpu-openblas",
    ]
    assert profile["model_vram_budget_mb"] == {
        "llm": 2600,
        "embedding": 1200,
        "reranker": 1200,
    }


def test_verification_report_matches_contract_and_includes_redis():
    assert len(ENDPOINTS) == 11
    assert any(ep["id"] == "redis" for ep in ENDPOINTS)
    results = [
        {
            "id": ep["id"],
            "name": ep["name"],
            "url": ep["url"],
            "status_code": 200,
            "latency_ms": 1.0,
            "status": "PASS",
            "passed": True,
        }
        for ep in ENDPOINTS
    ]
    report = build_verification_report(results)
    assert report["status"] == "PASS"
    assert report["total_endpoints"] == 11
    assert report["passed_endpoints"] == 11
    assert report["failed_endpoints"] == 0
