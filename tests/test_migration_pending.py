"""T097--T102 pending convergence tests.

These tests intentionally exercise the packaging and restore seams without
requiring a live Docker daemon or GPU.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import make_migration_pack as pack  # noqa: E402
from make_migration_pack import (  # noqa: E402
    build_manifest_inputs,
    step_3_build_dist_bundle,
)
from migration_pack.scripts import bootstrap_restore as restore  # noqa: E402
from migration_pack.scripts.normalize_compose import (  # noqa: E402
    normalize_compose_content,
)


def _minimal_project(root: Path) -> None:
    (root / "migration_pack" / "database").mkdir(parents=True)
    (root / "migration_pack" / "volumes").mkdir(parents=True)
    (root / "bteam").mkdir()
    (root / "ateam").mkdir()
    (root / "bteam" / "reset_pass.sql").write_text("reset\n", encoding="utf-8")
    (root / "bteam" / "oliview_project_backup_0813.sql").write_text(
        "backup\n", encoding="utf-8"
    )
    (root / "ateam" / "pilos_v2.sql").write_text("pilos\n", encoding="utf-8")
    (root / "docker-compose.yml").write_text("services:\n", encoding="utf-8")


def test_pending_pack_includes_generated_artifacts_and_required_bind_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _minimal_project(tmp_path)
    (tmp_path / "migration_pack" / "database" / "cosmetic_db.sql.gz").write_bytes(
        b"db"
    )
    (tmp_path / "migration_pack" / "volumes" / "green_mysql_data.tar.gz").write_bytes(
        b"volume"
    )
    monkeypatch.setattr(pack, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pack, "DB_DIR", tmp_path / "migration_pack" / "database")
    monkeypatch.setattr(pack, "VOL_DIR", tmp_path / "migration_pack" / "volumes")

    bundle = tmp_path / "dist" / "AISERVICE_Migration_Pack"
    step_3_build_dist_bundle(bundle, include_volumes=True)

    assert (bundle / "migration_pack/database/cosmetic_db.sql.gz").is_file()
    assert (bundle / "migration_pack/volumes/green_mysql_data.tar.gz").is_file()
    assert (bundle / "bteam/oliview_project_backup_0813.sql").is_file()
    assert (bundle / "bteam/reset_pass.sql").is_file()
    assert (bundle / "ateam/pilos_v2.sql").is_file()


def test_include_models_records_size_and_sha256_and_preserves_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _minimal_project(tmp_path)
    model = tmp_path / "model_gateway" / "models" / "qwen" / "model.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"weights")
    cache = model.parent / ".cache" / "download.lock"
    cache.parent.mkdir()
    cache.write_text("cache", encoding="utf-8")
    monkeypatch.setattr(pack, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pack, "DB_DIR", tmp_path / "migration_pack" / "database")
    monkeypatch.setattr(pack, "VOL_DIR", tmp_path / "migration_pack" / "volumes")

    bundle = tmp_path / "dist" / "AISERVICE_Migration_Pack"
    step_3_build_dist_bundle(bundle, include_models=True)
    manifest_models = pack.collect_model_files(bundle)

    bundled_model = bundle / "model_gateway/models/qwen/model.gguf"
    assert bundled_model.read_bytes() == b"weights"
    assert not (bundle / "model_gateway/models/qwen/.cache/download.lock").exists()
    assert manifest_models == [
        {
            "path": "model_gateway/models/qwen/model.gguf",
            "size_bytes": len(b"weights"),
            "sha256": hashlib.sha256(b"weights").hexdigest(),
        }
    ]
    inputs = build_manifest_inputs(
        project_root=bundle,
        databases=[],
        volumes=[],
        target_cpu="i7-930",
        target_gpu="gtx1070",
        models=manifest_models,
    )
    assert inputs["models"] == manifest_models
    manifest = pack.step_4_generate_manifest(
        bundle,
        databases=[],
        volumes=[],
        target_cpu="i7-930",
        target_gpu="gtx1070",
        models=manifest_models,
    )
    assert manifest["models"] == manifest_models
    assert "model_gateway/models/qwen/model.gguf" in manifest["checksums"]


def test_jit_contract_reaches_compiler_and_has_valid_heredoc():
    profile = pack._target_hardware("i7-930", "gtx1070")
    assert "-march=native" in profile["llama_cpp_flags"]

    script = (ROOT_DIR / "model_gateway" / "scripts" / "build_llama.sh").read_text(
        encoding="utf-8"
    )
    python_block = script.split("<<'PY'", 1)[1].split("\nPY", 1)[0]
    assert "detect_vllm_status()" not in python_block
    assert "-march=native" in script
    assert "-DCMAKE_CUDA_ARCHITECTURES=${cuda_arch}" in script
    assert "--version" in script


def test_green_restore_resolves_prefixed_containers_and_volumes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(
        restore,
        "resolve_running_container",
        lambda name: {
            "mysql-green": "bteam-green-mysql-green-1",
            "redis-green": "bteam-green-redis-green-1",
        }.get(name),
    )
    monkeypatch.setattr(
        restore,
        "resolve_existing_volume_name",
        lambda name, _container=None: name,
    )
    green_compose = tmp_path / "docker-compose.green.yml"
    green_compose.write_text("name: bteam-green\n", encoding="utf-8")
    targets = [
        {
            "container": "mysql-green",
            "db_name": "cosmetic_db",
            "user": "u",
            "password": "p",
            "root_password": "rp",
            "volume_name": "green_mysql_data",
            "dump_path": "database/cosmetic_db.sql.gz",
        }
    ]

    resolved = restore.resolve_restore_targets(
        targets, green_compose=green_compose
    )
    assert resolved[0]["container"] == "bteam-green-mysql-green-1"
    assert resolved[0]["resolved_volume_name"] == "bteam-green_green_mysql_data"
    assert restore.resolve_green_container("redis-green") == "bteam-green-redis-green-1"


def test_cpu_only_compose_removes_gpu_requirements_and_sets_runtime_mode():
    compose = """
services:
  vllm-serv:
    container_name: vllm-serv-gateway
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    devices:
      - /dev/dxg:/dev/dxg
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility
"""
    normalized = normalize_compose_content(compose, cpu_only=True)
    assert "deploy:" not in normalized
    assert "driver: nvidia" not in normalized
    assert "/dev/dxg" not in normalized
    assert "NVIDIA_VISIBLE_DEVICES" not in normalized
    assert "MODEL_GATEWAY_CPU_ONLY=1" in normalized
    assert "AISERVICE_SKIP_GPU=1" in normalized


def test_bootstrap_propagates_skip_gpu_and_degraded_report_reason():
    script_path = ROOT_DIR / "migration_pack" / "scripts" / "bootstrap_restore.sh"
    script = script_path.read_text(encoding="utf-8")
    assert "--cpu-only" in script
    assert "RESTORE_ARGS+=(--skip-gpu)" in script
    verify_path = ROOT_DIR / "migration_pack" / "scripts" / "verify_migration.py"
    verify = verify_path.read_text(encoding="utf-8")
    assert "--degraded-reason" in verify
