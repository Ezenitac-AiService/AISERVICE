#!/usr/bin/env python3
"""AISERVICE Windows -> Ubuntu 마이그레이션 팩 빌더 v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from migration_pack.scripts.env_utils import (
    load_environment,
    mask_secret,
    required_environment,
)

PROJECT_ROOT = Path(__file__).resolve().parent
MIGRATION_PACK_DIR = PROJECT_ROOT / "migration_pack"
DB_DIR = MIGRATION_PACK_DIR / "database"
VOL_DIR = MIGRATION_PACK_DIR / "volumes"
SCRIPTS_DIR = MIGRATION_PACK_DIR / "scripts"
DIST_DIR = PROJECT_ROOT / "dist"

EXCLUDE_DIR_NAMES: set[str] = {
    ".git",
    ".github",
    ".agents",
    ".specify",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
}
EXCLUDE_EXTENSIONS: set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
    ".tmp",
    ".swp",
    ".ds_store",
    ".safetensors",
    ".pt",
    ".pth",
    ".bin",
    ".onnx",
    ".gguf",
    ".weights",
}
MODEL_DIR_NAMES = {"models", "checkpoints"}
EXCLUDE_PATTERNS = EXCLUDE_DIR_NAMES
REQUIRED_ENV_KEYS = [
    "PILOS_DB_USER",
    "PILOS_DB_PASSWORD",
    "PILOS_DB_ROOT_PASSWORD",
    "PILOS_DB_NAME",
    "BTEAM_DB_USER",
    "BTEAM_DB_PASSWORD",
    "BTEAM_DB_ROOT_PASSWORD",
    "BTEAM_DB_NAME",
    "DUCKDNS_DOMAIN",
    "DUCKDNS_TOKEN",
]


class MigrationPackError(RuntimeError):
    """CLI 계약의 종료 코드와 연결된 빌드 오류."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def should_exclude_path(
    rel_path: Path | str,
    base_dir: Path | str = PROJECT_ROOT,
    *,
    include_models: bool = False,
) -> bool:
    """클린 번들에서 제외할 경로인지 판별합니다."""
    del base_dir
    path_obj = Path(rel_path)
    normalized = path_obj.as_posix().lstrip("./")
    if normalized in {".env", "ddns/.env"}:
        return False
    parts = set(path_obj.parts)
    if parts.intersection(EXCLUDE_DIR_NAMES):
        return True
    if not include_models and any(
        part in MODEL_DIR_NAMES or part.startswith("checkpoint-") for part in parts
    ):
        return True
    return path_obj.suffix.lower() in EXCLUDE_EXTENSIONS and not include_models


def log_step(title: str) -> None:
    print("\n" + "=" * 75)
    print(f" ▶ {title}")
    print("=" * 75)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AISERVICE Master Migration Pack Builder Engine v2.0"
    )
    parser.add_argument(
        "--output-dir", default=str(DIST_DIR), help="패키징 산출물 디렉터리"
    )
    parser.add_argument(
        "--skip-dump",
        action="store_true",
        help="신규 DB 덤프를 생략하고 기존 산출물 사용",
    )
    parser.add_argument(
        "--include-volumes",
        action="store_true",
        default=True,
        help="Docker named volume 포함",
    )
    parser.add_argument(
        "--no-volumes",
        action="store_false",
        dest="include_volumes",
        help="Docker volume 제외",
    )
    parser.add_argument(
        "--include-models", action="store_true", help="대용량 모델 파일 포함"
    )
    parser.add_argument("--target-os", default="ubuntu", help="타겟 OS 프로파일")
    parser.add_argument("--target-cpu", default="i7-930", help="타겟 CPU 프로파일")
    parser.add_argument("--target-gpu", default="gtx1070", help="타겟 GPU 프로파일")
    parser.add_argument("--dry-run", action="store_true", help="사전검사만 수행")
    parser.add_argument(
        "--force", "-f", action="store_true", help="기존 산출물 덮어쓰기 및 무인 실행"
    )
    parser.add_argument(
        "--format",
        choices=["tar.gz", "zip", "both"],
        default="both",
        help="아카이브 형식",
    )
    parser.add_argument(
        "--no-archive", action="store_true", help="압축 없이 bundle 디렉터리만 유지"
    )
    return parser


def _run(
    command: list[str],
    *,
    cwd: Path = PROJECT_ROOT,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, cwd=cwd, env=dict(env) if env else None, text=True, check=True
        )
    except FileNotFoundError as exc:
        raise MigrationPackError(
            f"필수 실행 파일을 찾을 수 없습니다: {command[0]}", 1
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise MigrationPackError(
            f"명령 실행 실패(code={exc.returncode}): {command[0]}", 2
        ) from exc


def preflight_environment(
    project_root: Path | str = PROJECT_ROOT,
    output_dir: Path | str = DIST_DIR,
    *,
    include_volumes: bool = True,
    skip_dump: bool = False,
    check_docker: bool = False,
) -> tuple[int, list[str]]:
    """패키징 전에 선언된 환경/디스크/도커 요구사항을 검사하고 계약 종료 코드를 반환합니다."""
    root = Path(project_root).resolve()
    out = Path(output_dir).resolve()
    env = load_environment(root)
    issues: list[str] = []
    required = (
        REQUIRED_ENV_KEYS if not skip_dump else ["DUCKDNS_DOMAIN", "DUCKDNS_TOKEN"]
    )
    missing = required_environment(env, required)
    if missing:
        issues.extend(f"환경 변수 누락: {key}" for key in missing)
        return 1, issues

    for required_path in [
        root / "docker-compose.yml",
        root / "migration_pack",
        root / "migration_pack" / "scripts",
    ]:
        if not required_path.exists():
            issues.append(f"필수 경로 누락: {required_path}")
            return 1, issues

    # 디스크 여유 공간 검사 (Exit Code 4)
    try:
        out.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(out).free < 25 * 1024**3:
            issues.append(f"출력 디스크 여유 공간이 25GB 미만입니다 ({shutil.disk_usage(out).free / (1024**3):.1f}GB)")
            return 4, issues
    except OSError as exc:
        issues.append(f"출력 디렉터리 확인 실패: {exc}")
        return 4, issues

    # Docker 데몬 및 볼륨 검사 (Exit Code 3)
    if not skip_dump and include_volumes and check_docker:
        try:
            subprocess.run(
                ["docker", "info"],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            issues.append("Docker daemon에 연결할 수 없습니다")
            return 3, issues

    return 0, issues


def _read_export_metadata() -> list[dict[str, Any]]:
    metadata_path = DB_DIR / "database_export_manifest.json"
    if metadata_path.is_file():
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return []


def step_1_export_databases(
    *, skip_dump: bool = False, environment: Mapping[str, str] | None = None
) -> list[dict[str, Any]]:
    log_step("[1/5] 일관성 보장 DB 논리 덤프 추출")
    if skip_dump:
        print("  ⏩ --skip-dump 지정으로 DB 추출을 생략합니다.")
    else:
        export_script = SCRIPTS_DIR / "export_databases.py"
        if not export_script.is_file():
            raise MigrationPackError(f"DB export script not found: {export_script}", 2)
        child_env = dict(environment or load_environment(PROJECT_ROOT))
        _run([sys.executable, str(export_script)], env=child_env)

    measured = {str(item.get("name")): item for item in _read_export_metadata()}
    results: list[dict[str, Any]] = []
    for db_file in sorted(DB_DIR.glob("*.sql.gz")):
        db_name = db_file.name.removesuffix(".sql.gz")
        measured_item = measured.get(db_name, {})
        results.append(
            {
                "name": db_name,
                "dump_file": f"database/{db_file.name}",
                "size_bytes": db_file.stat().st_size,
                "sha256": hashlib.sha256(db_file.read_bytes()).hexdigest(),
                "row_count": int(measured_item.get("row_count", 0)),
                "row_count_source": measured_item.get(
                    "row_count_source", "unavailable"
                ),
            }
        )
    if not skip_dump and not results:
        raise MigrationPackError("DB 덤프 산출물이 생성되지 않았습니다", 2)
    return results


def step_2_export_volumes(*, include_volumes: bool = True) -> list[dict[str, Any]]:
    log_step("[2/5] Docker named volume 물리 아카이브 추출")
    if not include_volumes:
        print("  ⏩ --no-volumes 지정으로 볼륨 추출을 생략합니다.")
        return []
    from migration_pack.scripts.export_docker_volumes import export_all_managed_volumes

    try:
        return export_all_managed_volumes(VOL_DIR, strict=True)
    except Exception as exc:
        raise MigrationPackError(f"Docker volume export failed: {exc}", 3) from exc


def _copy_tree_clean(
    src_folder: Path, bundle_dir: Path, *, include_models: bool
) -> tuple[int, int]:
    included_count = 0
    total_bytes = 0
    for root, dirs, files in os.walk(src_folder):
        root_path = Path(root)
        rel_root = root_path.relative_to(PROJECT_ROOT)
        dirs[:] = [
            d
            for d in dirs
            if not should_exclude_path(rel_root / d, include_models=include_models)
        ]
        for file in files:
            src_file = root_path / file
            rel_path = src_file.relative_to(PROJECT_ROOT)
            if should_exclude_path(rel_path, include_models=include_models):
                continue
            dest_file = bundle_dir / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            included_count += 1
            total_bytes += src_file.stat().st_size
    return included_count, total_bytes


def step_3_build_dist_bundle(
    bundle_dir: Path,
    target_os: str = "ubuntu",
    *,
    include_models: bool = False,
    overwrite: bool = True,
) -> int:
    del target_os
    log_step("[3/5] 클린 소스 번들 조립 및 실사용 환경 파일 보존")
    if bundle_dir.exists():
        if not overwrite:
            raise MigrationPackError(f"기존 bundle이 있습니다: {bundle_dir}", 1)
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    included_count = 0
    total_bytes = 0
    core_folders = [
        "ateam",
        "bteam",
        "model_gateway",
        "gateway",
        "config",
        "ddns",
        "tests",
        "docs",
        "migration_pack",
    ]
    core_files = [
        ".env",
        "docker-compose.yml",
        "run_all_services.bat",
        "run_all_services.sh",
        "README.md",
        "LICENSE",
    ]

    for item in core_files:
        src = PROJECT_ROOT / item
        if src.is_file() and not should_exclude_path(
            Path(item), include_models=include_models
        ):
            dest = bundle_dir / item
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            included_count += 1
            total_bytes += src.stat().st_size

    for folder in core_folders:
        src_folder = PROJECT_ROOT / folder
        if not src_folder.is_dir():
            continue
        count, size = _copy_tree_clean(
            src_folder, bundle_dir, include_models=include_models
        )
        included_count += count
        total_bytes += size

    # 내부 구현 스크립트가 루트 wrapper를 덮어쓰지 않도록 원본 wrapper만 복사합니다.
    root_wrapper = PROJECT_ROOT / "bootstrap_restore.sh"
    if root_wrapper.is_file():
        shutil.copy2(root_wrapper, bundle_dir / root_wrapper.name)
        included_count += 1
        total_bytes += root_wrapper.stat().st_size

    print(
        f"  ✓ {included_count:,}개 파일, {total_bytes / (1024 * 1024):.1f}MB 조립 완료"
    )
    return included_count


def _target_hardware(target_cpu: str, target_gpu: str) -> dict[str, Any]:
    gpu_label = (
        "NVIDIA GeForce GTX 1070 8GB (Pascal sm_61)"
        if target_gpu.lower() in {"gtx1070", "sm_61", "61"}
        else target_gpu
    )
    cpu_label = (
        "Intel Core i7-930 (SSE4.2, Non-AVX)"
        if target_cpu.lower() == "i7-930"
        else target_cpu
    )
    return {
        "cpu": cpu_label,
        "gpu": gpu_label,
        "ram_mb": 24576,
        "vram_mb": 8192 if gpu_label != "none" else 0,
        "llama_cpp_flags": "-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61 -DGGML_AVX=OFF -DGGML_AVX2=OFF",
        "vram_safety_limit_mb": 5000,
    }


def build_manifest_inputs(
    *,
    project_root: Path | str,
    databases: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    target_cpu: str,
    target_gpu: str,
    environment: Mapping[str, str] | None = None,
    checksums: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    env = dict(environment or load_environment(root))
    return {
        "source_environment": {
            "os": platform.system(),
            "platform": platform.platform(),
            "hostname": platform.node(),
        },
        "target_hardware": _target_hardware(target_cpu, target_gpu),
        "databases": databases,
        "volumes": volumes,
        "ddns_config": {
            "domain": env.get("DUCKDNS_DOMAIN", ""),
            "token": mask_secret(env.get("DUCKDNS_TOKEN")),
            "token_present": bool(env.get("DUCKDNS_TOKEN")),
            "cron_interval_minutes": 5,
        },
        "services": [
            "gateway",
            "vllm-serv",
            "redis",
            "bteam_db",
            "oliview_backend",
            "oliview_frontend",
            "oliview_chatbot_a",
            "oliview_chatbot_b",
            "pilos_db",
            "pilos_web",
            "pilos_worker",
        ],
        "checksums": checksums or {},
    }


def _relative_bundle_files(bundle_dir: Path) -> Iterable[tuple[Path, str]]:
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(bundle_dir).as_posix()
        if rel in {
            "migration_pack/migration_manifest.json",
            "migration_pack/checksums.sha256",
        }:
            continue
        yield path, rel


def _inventory_digest(checksums: Mapping[str, str]) -> str:
    canonical = "\n".join(f"{key}  {checksums[key]}" for key in sorted(checksums))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def step_4_generate_manifest(
    bundle_dir: Path,
    databases: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    target_cpu: str = "i7-930",
    target_gpu: str = "gtx1070",
    *,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    log_step("[4/5] Manifest v2 및 전체 산출물 SHA-256 생성")
    from migration_pack.scripts.manifest_utils import (
        build_manifest_v2,
        generate_checksums_file,
        validate_manifest_schema,
    )

    cs_path = bundle_dir / "migration_pack" / "checksums.sha256"
    checksum_map = generate_checksums_file(
        list(_relative_bundle_files(bundle_dir)), cs_path
    )
    inputs = build_manifest_inputs(
        project_root=bundle_dir,
        databases=databases,
        volumes=volumes,
        target_cpu=target_cpu,
        target_gpu=target_gpu,
        environment=environment,
        checksums=checksum_map,
    )
    manifest = build_manifest_v2(
        source_env=inputs["source_environment"],
        target_hardware=inputs["target_hardware"],
        databases=inputs["databases"],
        volumes=inputs["volumes"],
        ddns_config=inputs["ddns_config"],
        services=inputs["services"],
        checksums=inputs["checksums"],
    )
    manifest["source_bundle"] = {
        "file_count": len(checksum_map),
        "sha256": _inventory_digest(checksum_map),
    }
    valid, errors = validate_manifest_schema(manifest)
    if not valid:
        raise MigrationPackError(
            "Manifest schema validation failed: " + "; ".join(errors), 5
        )
    manifest_path = bundle_dir / "migration_pack" / "migration_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"  ✓ Manifest: {manifest_path}")
    print(f"  ✓ Checksums: {cs_path} ({len(checksum_map)}개)")
    return manifest


def step_5_create_archive(
    bundle_dir: Path,
    output_dir: Path,
    fmt: str = "both",
    *,
    force: bool = False,
) -> Path | list[Path]:
    log_step("[5/5] 최종 마이그레이션 아카이브 생성")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = f"AISERVICE_Migration_Pack_{timestamp}"
    formats = ["tar.gz", "zip"] if fmt == "both" else [fmt]
    archives: list[Path] = []
    for archive_format in formats:
        archive_path = output_dir / f"{base_name}.{archive_format}"
        if archive_path.exists() and not force:
            raise MigrationPackError(
                f"기존 아카이브가 있습니다: {archive_path}. --force로 덮어쓸 수 있습니다.",
                1,
            )
        if archive_format == "tar.gz":
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(bundle_dir, arcname="AISERVICE")
        else:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
                for path in bundle_dir.rglob("*"):
                    if path.is_file():
                        zip_out.write(
                            path,
                            arcname=str(
                                Path("AISERVICE") / path.relative_to(bundle_dir)
                            ),
                        )
        archives.append(archive_path)
        print(
            f"  ✓ {archive_path} ({archive_path.stat().st_size / (1024 * 1024):.1f}MB)"
        )
    return archives[0] if len(archives) == 1 else archives


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    out_dir = Path(args.output_dir).resolve()
    environment = load_environment(PROJECT_ROOT)
    print(
        f"AISERVICE Migration Pack v2 | source={PROJECT_ROOT} | target={args.target_os}/{args.target_cpu}/{args.target_gpu}"
    )
    code, issues = preflight_environment(
        PROJECT_ROOT,
        out_dir,
        include_volumes=args.include_volumes,
        skip_dump=args.skip_dump,
        check_docker=not args.dry_run,
    )
    if code != 0:
        for issue in issues:
            print(f"[ERROR] {issue}", file=sys.stderr)
        return code
    if args.dry_run:
        print("[DRY-RUN] =======================================================")
        print(f"[DRY-RUN] Target OS: {args.target_os}, CPU: {args.target_cpu}, GPU: {args.target_gpu}")
        print(f"[DRY-RUN] Include Volumes: {args.include_volumes}, Include Models: {args.include_models}")
        print(f"[DRY-RUN] Output Directory: {out_dir}")
        print(f"[DRY-RUN] Disk Space Available: {shutil.disk_usage(out_dir).free / (1024**3):.1f}GB (>= 25GB REQUIRED)")
        print("[DRY-RUN] Preflight checks PASSED (Exit Code 0). 실제 산출물은 생성하지 않았습니다.")
        print("[DRY-RUN] =======================================================")
        return 0

    start = time.time()
    try:
        db_results = step_1_export_databases(
            skip_dump=args.skip_dump, environment=environment
        )
        vol_results = step_2_export_volumes(include_volumes=args.include_volumes)
        bundle_dir = out_dir / "AISERVICE_Migration_Pack"
        step_3_build_dist_bundle(
            bundle_dir,
            args.target_os,
            include_models=args.include_models,
            overwrite=args.force,
        )
        step_4_generate_manifest(
            bundle_dir,
            db_results,
            vol_results,
            args.target_cpu,
            args.target_gpu,
            environment=environment,
        )
        result: Path | list[Path] = (
            bundle_dir
            if args.no_archive
            else step_5_create_archive(
                bundle_dir, out_dir, args.format, force=args.force
            )
        )
        print(f"완료: {result} ({time.time() - start:.1f}s)")
        return 0
    except MigrationPackError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return exc.exit_code
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"[ERROR] 예상하지 못한 패키징 오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
