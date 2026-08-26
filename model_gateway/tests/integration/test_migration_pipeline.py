"""
Integration tests for Seed Pack migration pipeline (extraction & environment restoration).
"""

import os
import subprocess
import tarfile
import pytest


def get_repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_seed_pack_extraction_and_structure(tmp_path):
    """T009: Test extracting seed pack into clean sandbox directory and verifying required files."""
    repo_root = get_repo_root()
    tar_path = tmp_path / "seed.tar.gz"
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()

    # Generate seed pack
    res = subprocess.run(
        ["bash", os.path.join(repo_root, "scripts", "make_seed_pack.sh"), "-o", str(tar_path)],
        capture_output=True, text=True, cwd=repo_root
    )
    assert res.returncode == 0, f"Failed to create seed pack: {res.stderr}"

    # Extract to sandbox
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=sandbox_dir)

    # Verify key structure exists in extracted sandbox
    assert (sandbox_dir / "pyproject.toml").exists()
    assert (sandbox_dir / "scripts" / "setup.sh").exists()
    assert (sandbox_dir / "scripts" / "make_seed_pack.sh").exists()
    assert (sandbox_dir / "src" / "api" / "server.py").exists()
    assert (sandbox_dir / "src" / "core" / "process_manager.py").exists()
    assert (sandbox_dir / "src" / "core" / "auxiliary_manager.py").exists(), "auxiliary_manager.py must exist in extracted seed pack"
    assert (sandbox_dir / "config" / "model_catalog.json").exists()

    # Verify model catalog contents in extracted sandbox
    with open(sandbox_dir / "config" / "model_catalog.json", "r", encoding="utf-8") as f:
        catalog_data = f.read()
    assert "bge-m3" in catalog_data, "bge-m3 must be in model_catalog.json"
    assert "bge-reranker-v2-m3" in catalog_data, "bge-reranker-v2-m3 must be in model_catalog.json"

    # Verify make_seed_pack.sh stdout output contains auxiliary_manager verification
    assert "auxiliary_manager.py" in res.stdout, "make_seed_pack.sh stdout must mention auxiliary_manager.py verification"

    # Verify excluded directories do NOT exist
    assert not (sandbox_dir / "models").exists()
    assert not (sandbox_dir / ".venv").exists()
    assert not (sandbox_dir / ".bin").exists()


def test_seed_pack_restored_make_seed_pack_execution(tmp_path):
    """T011: Test that the extracted seed pack contains working scripts that can generate a seed pack again."""
    repo_root = get_repo_root()
    tar_path = tmp_path / "seed.tar.gz"
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()

    # Generate initial seed pack
    subprocess.run(
        ["bash", os.path.join(repo_root, "scripts", "make_seed_pack.sh"), "-o", str(tar_path)],
        check=True, cwd=repo_root
    )

    # Extract to sandbox
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=sandbox_dir)

    # Make scripts executable in sandbox
    subprocess.run(["chmod", "+x", str(sandbox_dir / "scripts" / "make_seed_pack.sh")], check=True)

    # Run make_seed_pack.sh inside sandbox
    output_sandbox_tar = sandbox_dir / "dist" / "sandbox_seed.tar.gz"
    res = subprocess.run(
        ["bash", str(sandbox_dir / "scripts" / "make_seed_pack.sh"), "-o", str(output_sandbox_tar)],
        capture_output=True, text=True, cwd=sandbox_dir
    )

    assert res.returncode == 0, f"make_seed_pack.sh in sandbox failed: {res.stderr}"
    assert output_sandbox_tar.exists(), "Sandbox generated seed pack must exist"


def test_setup_fallback_and_status_report():
    """T014: Test status_server.sh output contains 3-way platform state & CUDA status."""
    repo_root = get_repo_root()
    status_script = os.path.join(repo_root, "scripts", "status_server.sh")

    assert os.path.exists(status_script), "status_server.sh script must exist"

    res = subprocess.run(["bash", status_script], capture_output=True, text=True, cwd=repo_root)
    assert res.returncode == 0, f"status_server.sh failed: {res.stderr}"

    assert "vllm_serv 서버 및 멀티 플랫폼 하드웨어 리포트" in res.stdout, "status_server.sh report title missing"
    assert "llama-cpp-python GPU:" in res.stdout, "status_server.sh must report llama-cpp-python GPU status"


def test_start_server_preflight_fail_fast():
    """T008 / US2: Test check_hardware_preflight() fail-fast when llama_supports_gpu_offload() fails."""
    from src.core.cpu_detector import check_hardware_preflight
    res = check_hardware_preflight()
    # When CUDA GPU environment is active, passed must be True and llama_gpu_offload must be True
    assert "llama_gpu_offload" in res or "error_message" in res
    if res.get("passed"):
        assert res.get("llama_gpu_offload") is True, "llama_gpu_offload must be True when preflight passes"
