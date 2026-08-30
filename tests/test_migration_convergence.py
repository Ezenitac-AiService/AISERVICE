"""T038--T050 수렴 작업의 회귀/계약 테스트."""

from __future__ import annotations

import gzip
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

from make_migration_pack import (
    build_argument_parser,
    build_manifest_inputs,
    preflight_environment,
    step_5_create_archive,
)
from migration_pack.scripts.archive_crypto import decrypt_file, encrypt_file
from migration_pack.scripts.bootstrap_restore import (
    decrypt_and_extract_archive,
    get_restore_targets,
    normalize_extracted_permissions,
    restore_database_dump,
)
from migration_pack.scripts.env_utils import load_environment, mask_secret
from migration_pack.scripts.export_docker_volumes import get_managed_volumes_map
from migration_pack.scripts.export_docker_volumes import (
    VolumeExportError,
    pre_flush_service_state,
)
from migration_pack.scripts.export_databases import get_database_targets
from migration_pack.scripts.verify_migration import (
    ENDPOINTS,
    build_argument_parser as build_verify_argument_parser,
    build_verification_report,
    test_endpoint,
)
from model_gateway.scripts.probe_hardware import generate_build_profile
from model_gateway.src.config import (
    attempt_runtime_backends,
    clamp_vram_safety_limit,
    is_runtime_compatibility_error,
    select_runtime_backend,
)


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


def test_migration_cli_parser_defaults_to_encrypted_tarball_and_accepts_key_file():
    parser = build_argument_parser()
    args = parser.parse_args(["--key-file", "key.bin"])

    assert args.format == "tar.gz"
    assert args.key_file == "key.bin"


def test_archive_crypto_round_trip_and_authenticated_failure(tmp_path: Path):
    source = tmp_path / "payload.txt"
    encrypted = tmp_path / "payload.enc"
    restored = tmp_path / "restored.txt"
    source.write_text("secret payload\n", encoding="utf-8")

    encrypt_file(source, encrypted, b"test-key")
    decrypt_file(encrypted, restored, b"test-key")

    assert restored.read_text(encoding="utf-8") == "secret payload\n"
    with pytest.raises(ValueError, match="인증 실패"):
        decrypt_file(encrypted, tmp_path / "wrong.txt", b"wrong-key")


def test_pack_archive_is_encrypted_and_decryptable_without_plain_temp_file(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "migration_pack").mkdir(parents=True)
    (bundle / ".env").write_text("DB_PASSWORD=secret-value\n", encoding="utf-8")
    (bundle / "migration_pack" / "migration_manifest.json").write_text(
        '{"archive_encrypted": true}\n', encoding="utf-8"
    )
    key_path = tmp_path / "key.bin"
    key_path.write_bytes(b"external-key")
    output = tmp_path / "dist"

    archive = step_5_create_archive(bundle, output, "tar.gz", key_file=key_path)

    assert archive.suffix == ".enc"
    assert not list(output.glob("*.plain"))
    decrypted = tmp_path / "decrypted.tar.gz"
    decrypt_file(archive, decrypted, b"external-key")
    with tarfile.open(decrypted, "r:gz") as tar:
        names = tar.getnames()
    assert "AISERVICE/.env" in names
    assert b"secret-value" not in archive.read_bytes()


def test_bootstrap_decrypt_and_extract_rejects_path_escape(tmp_path: Path):
    plain = tmp_path / "payload.tar.gz"
    with tarfile.open(plain, "w:gz") as tar:
        data = b"unsafe"
        info = tarfile.TarInfo("../outside.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    encrypted = tmp_path / "payload.tar.gz.enc"
    encrypt_file(plain, encrypted, b"external-key")
    (tmp_path / "key.bin").write_bytes(b"external-key")

    with pytest.raises(Exception, match="벗어납니다"):
        decrypt_and_extract_archive(encrypted, tmp_path / "extract", tmp_path / "key.bin")


def test_direct_archive_extraction_normalizes_env_and_script_permissions(tmp_path: Path):
    bundle_root = tmp_path / "AISERVICE"
    (bundle_root / "ddns").mkdir(parents=True)
    (bundle_root / "migration_pack" / "scripts").mkdir(parents=True)
    env_path = bundle_root / ".env"
    ddns_env_path = bundle_root / "ddns" / ".env"
    script_path = bundle_root / "migration_pack" / "scripts" / "bootstrap_restore.sh"
    for path in (env_path, ddns_env_path, script_path):
        path.write_text("content\n", encoding="utf-8")

    chmod_calls: list[tuple[Path, int]] = []
    original_chmod = os.chmod

    def record_chmod(path, mode, **_kwargs):
        chmod_calls.append((Path(path), mode))
        original_chmod(path, mode)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(os, "chmod", record_chmod)
    normalized = normalize_extracted_permissions(tmp_path)
    monkeypatch.undo()

    assert normalized == bundle_root
    assert (env_path, 0o600) in chmod_calls
    assert (ddns_env_path, 0o600) in chmod_calls
    assert any(path == script_path and mode == 0o755 for path, mode in chmod_calls)


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


def test_manifest_inputs_declares_archive_security_without_plaintext_secret():
    inputs = build_manifest_inputs(
        project_root=Path("."),
        databases=[],
        volumes=[],
        target_cpu="i7-930",
        target_gpu="sm_61",
        environment={"DUCKDNS_TOKEN": "super-secret"},
        archive_format="tar.gz",
    )

    assert inputs["archive_format"] == "tar.gz"
    assert inputs["archive_encrypted"] is True
    assert inputs["archive_provider"] == "stdlib-pbkdf2-hmac-sha256"
    assert inputs["archive_envelope"] == "AISERVICE-MIGRATION-ARCHIVE-V1"
    assert inputs["secrets"]["plaintext_excluded"] is True
    assert "super-secret" not in json.dumps(inputs)


def test_bootstrap_shell_closes_option_parser_before_execution():
    script = (ROOT_DIR / "migration_pack" / "scripts" / "bootstrap_restore.sh").read_text(
        encoding="utf-8"
    )
    parser_end = script.index("log_info \"AISERVICE Ubuntu bootstrap")
    assert "done" in script[script.index("while "):parser_end].splitlines()


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
        "BTEAM_DB_PASSWORD=olive-secret\n"
        "GREEN_DB_NAME=cosmetic_db\n"
        "GREEN_DB_USER=bteam_green\n"
        "GREEN_DB_PASSWORD=green-secret\n"
        "GREEN_DB_ROOT_PASSWORD=green-root\n",
        encoding="utf-8",
    )

    targets = get_restore_targets(tmp_path)

    assert targets[0]["container"] == "pilos-custom"
    assert targets[0]["db_name"] == "custom_pilos"
    assert targets[1]["password"] == "olive-secret"


def test_green_database_is_mandatory_for_export_and_restore(tmp_path: Path):
    environment = {
        "PILOS_DB_NAME": "pilos_v2",
        "PILOS_DB_USER": "pilos",
        "PILOS_DB_PASSWORD": "pilos-secret",
        "PILOS_DB_ROOT_PASSWORD": "pilos-root",
        "BTEAM_DB_NAME": "oliview_project",
        "BTEAM_DB_USER": "oliview",
        "BTEAM_DB_PASSWORD": "oliview-secret",
        "BTEAM_DB_ROOT_PASSWORD": "oliview-root",
        "GREEN_DB_NAME": "cosmetic_db",
        "GREEN_DB_USER": "bteam_green",
        "GREEN_DB_PASSWORD": "green-secret",
        "GREEN_DB_ROOT_PASSWORD": "green-root",
    }

    targets = get_database_targets(environment)
    assert [target["db_name"] for target in targets] == [
        "pilos_v2",
        "oliview_project",
        "cosmetic_db",
    ]
    (tmp_path / ".env").write_text(
        "\n".join(f"{key}={value}" for key, value in environment.items()) + "\n",
        encoding="utf-8",
    )
    restore_targets = get_restore_targets(tmp_path)
    assert restore_targets[-1]["container"] == "mysql-green"
    assert restore_targets[-1]["db_name"] == "cosmetic_db"


def test_preflight_checks_db_even_when_volumes_are_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    env = {
        "PILOS_DB_NAME": "pilos_v2",
        "PILOS_DB_USER": "pilos",
        "PILOS_DB_PASSWORD": "pilos-secret",
        "PILOS_DB_ROOT_PASSWORD": "pilos-root",
        "BTEAM_DB_NAME": "oliview_project",
        "BTEAM_DB_USER": "oliview",
        "BTEAM_DB_PASSWORD": "oliview-secret",
        "BTEAM_DB_ROOT_PASSWORD": "oliview-root",
        "GREEN_DB_NAME": "cosmetic_db",
        "GREEN_DB_USER": "bteam_green",
        "GREEN_DB_PASSWORD": "green-secret",
        "GREEN_DB_ROOT_PASSWORD": "green-root",
        "DUCKDNS_DOMAIN": "example",
        "DUCKDNS_TOKEN": "token",
    }
    (tmp_path / ".env").write_text(
        "\n".join(f"{key}={value}" for key, value in env.items()) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "migration_pack" / "scripts").mkdir(parents=True)
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return Result()

    class Disk:
        free = 30 * 1024**3

    monkeypatch.setattr("make_migration_pack.shutil.disk_usage", lambda _path: Disk())
    monkeypatch.setattr("make_migration_pack.subprocess.run", fake_run)
    monkeypatch.setattr("migration_pack.scripts.export_databases.check_container_running", lambda _container: True)
    monkeypatch.setattr("migration_pack.scripts.export_databases.check_database_connection", lambda _target: False)

    code, issues = preflight_environment(
        tmp_path, tmp_path / "out", include_volumes=False, check_docker=True
    )

    assert code == 2
    assert any("DB 연결" in issue for issue in issues)
    assert any(command[:2] == ["docker", "info"] for command in calls)


def test_chroma_checkpoint_precedes_vector_measurement_and_requires_running_container(
    monkeypatch: pytest.MonkeyPatch,
):
    events: list[str] = []
    monkeypatch.setattr(
        "migration_pack.scripts.export_docker_volumes._container_running",
        lambda _container: True,
    )
    monkeypatch.setattr(
        "migration_pack.scripts.export_docker_volumes.measure_chroma_vector_count",
        lambda _container: events.append("measure") or 48210,
    )

    class Result:
        returncode = 0
        stdout = ""

    def fake_run(command, **_kwargs):
        if command[1:3] == ["exec", "chroma-green"]:
            events.append("checkpoint")
        return Result()

    monkeypatch.setattr("migration_pack.scripts.export_docker_volumes.subprocess.run", fake_run)
    meta = {"associated_container": "chroma-green", "snapshot": "chroma"}
    state = pre_flush_service_state("green_chroma_data", meta)

    assert state["paused"] is True
    assert meta["vector_count"] == 48210
    assert events.index("checkpoint") < events.index("measure")

    monkeypatch.setattr(
        "migration_pack.scripts.export_docker_volumes._container_running",
        lambda _container: False,
    )
    with pytest.raises(VolumeExportError, match="실행 중"):
        pre_flush_service_state(
            "green_chroma_data",
            {"associated_container": "chroma-green", "snapshot": "chroma"},
        )


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


def test_verifier_requires_http_200_and_omits_error_on_success(monkeypatch):
    http_endpoints = [ep for ep in ENDPOINTS if ep["url"].startswith("http")]
    assert len(http_endpoints) == 10
    assert all(ep["expected_status"] == [200] for ep in http_endpoints)

    class Response:
        status = 200

        def getcode(self):
            return self.status

        def read(self, _limit):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "migration_pack.scripts.verify_migration.urllib.request.urlopen",
        lambda *args, **kwargs: Response(),
    )
    result = test_endpoint(http_endpoints[0])
    assert result["status"] == "PASS"
    assert "error" not in result


def test_verifier_rejects_http_redirect_and_uses_bundle_default_report_path():
    assert all(
        ep["expected_status"] == [200]
        for ep in ENDPOINTS
        if ep["url"].startswith("http")
    )
    args = build_verify_argument_parser().parse_args([])
    assert args.json_report.endswith("migration_pack\\verification_report.json")


def test_manifest_archive_formats_and_plaintext_secret_exclusion(tmp_path: Path):
    for archive_format in ("tar.gz", "zip", "both"):
        inputs = build_manifest_inputs(
            project_root=tmp_path,
            databases=[],
            volumes=[],
            target_cpu="i7-930",
            target_gpu="sm_61",
            environment={"DUCKDNS_TOKEN": "top-secret"},
            archive_format=archive_format,
        )
        assert inputs["archive_format"] == archive_format
        assert inputs["archive_encrypted"] is True
        assert inputs["archive_provider"] == "stdlib-pbkdf2-hmac-sha256"
        assert "top-secret" not in json.dumps(inputs)


def test_runtime_backend_selection_and_vram_clamp():
    assert clamp_vram_safety_limit("99999") == 5000
    assert clamp_vram_safety_limit("-1") == 0
    assert select_runtime_backend(
        {"vllm": False, "llama.cpp-cuda": True, "llama.cpp-cpu-openblas": True}
    ) == "llama.cpp-cuda"
    assert select_runtime_backend(
        {"vllm": False, "llama.cpp-cuda": False, "llama.cpp-cpu-openblas": True}
    ) == "llama.cpp-cpu-openblas"


def test_runtime_fallback_attempts_health_in_order_and_detects_compatibility_errors():
    attempted: list[str] = []

    def probe(backend: str) -> bool:
        attempted.append(backend)
        return backend == "llama.cpp-cpu-openblas"

    selected, failures = attempt_runtime_backends(probe)

    assert attempted == ["vllm", "llama.cpp-cuda", "llama.cpp-cpu-openblas"]
    assert selected == "llama.cpp-cpu-openblas"
    assert len(failures) == 2
    assert is_runtime_compatibility_error("CUDA mismatch: no kernel image") is True
    assert is_runtime_compatibility_error("normal startup message") is False
