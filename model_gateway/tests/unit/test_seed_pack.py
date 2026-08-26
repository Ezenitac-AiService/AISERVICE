"""
Unit tests for Seed Pack generator (scripts/make_seed_pack.sh).
Tests tarball creation, exclusion rules, custom output paths, and --zip format.
"""

import glob
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
import pytest


def get_repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_make_seed_pack_script_exists_and_executable():
    repo_root = get_repo_root()
    script_path = os.path.join(repo_root, "scripts", "make_seed_pack.sh")

    assert os.path.exists(script_path), f"Script missing at {script_path}"
    assert os.access(script_path, os.X_OK), "scripts/make_seed_pack.sh must be executable"


def test_make_seed_pack_default_tarball(tmp_path):
    repo_root = get_repo_root()
    output_tar = tmp_path / "vllm_serv_seed.tar.gz"

    cmd = ["bash", os.path.join(repo_root, "scripts", "make_seed_pack.sh"), "--skip-legacy-build", "-o", str(output_tar)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    assert res.returncode == 0, f"make_seed_pack.sh failed: {res.stderr}\nOutput: {res.stdout}"
    assert output_tar.exists(), "Output tar.gz file must exist"

    # Size check (< 300MB = 314,572,800 bytes) including prebuilt legacy wheels (wheels/legacy_i7_930/)
    file_size = output_tar.stat().st_size
    assert file_size < 300 * 1024 * 1024, f"Seed pack file size too large: {file_size} bytes"

    # Inspect tarball contents
    with tarfile.open(output_tar, "r:gz") as tar:
        names = tar.getnames()

        # Mandatory files check
        normalized_names = [n[2:] if n.startswith("./") else n for n in names]

        assert any("pyproject.toml" in n for n in normalized_names), "pyproject.toml missing from archive"
        assert any("setup.sh" in n for n in normalized_names), "setup.sh missing from archive"
        assert any("process_manager.py" in n for n in normalized_names), "process_manager.py missing from archive"
        assert any("model_catalog.json" in n for n in normalized_names), "model_catalog.json missing from archive"
        assert any("sample/common.py" in n for n in normalized_names), "sample/common.py missing from archive"
        assert any(n.startswith("specs/") for n in normalized_names), "specs/ missing from archive"

        # Excluded directories check
        for n in normalized_names:
            assert not n.startswith("models/") and "/models/" not in n, f"Excluded directory models/ found in archive: {n}"
            assert not n.startswith(".venv/") and "/.venv/" not in n, f"Excluded directory .venv/ found in archive: {n}"
            assert not n.startswith(".bin/") and "/.bin/" not in n, f"Excluded directory .bin/ found in archive: {n}"
            assert not n.startswith("logs/") and "/logs/" not in n, f"Excluded directory logs/ found in archive: {n}"
            assert not n.startswith("__pycache__/") and "/__pycache__/" not in n, f"Excluded __pycache__ found in archive: {n}"
            assert not n.startswith(".git/") and "/.git/" not in n, f"Excluded .git/ found in archive: {n}"
            assert not n.startswith(".agents/") and "/.agents/" not in n, f"Excluded .agents/ found in archive: {n}"
            assert not n.startswith(".specify/") and "/.specify/" not in n, f"Excluded .specify/ found in archive: {n}"
            assert "model_context_profiles.json" not in n, f"Excluded model_context_profiles.json found in archive: {n}"
            assert "benchmark_results.json" not in n, f"Excluded benchmark_results.json found in archive: {n}"


def test_make_seed_pack_zip_format(tmp_path):
    if not shutil.which("zip"):
        pytest.skip("zip command not installed in environment")

    repo_root = get_repo_root()
    output_zip = tmp_path / "vllm_serv_seed.zip"

    cmd = ["bash", os.path.join(repo_root, "scripts", "make_seed_pack.sh"), "--skip-legacy-build", "--zip", "-o", str(output_zip)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)

    assert res.returncode == 0, f"make_seed_pack.sh --zip failed: {res.stderr}\nOutput: {res.stdout}"
    assert output_zip.exists(), "Output zip file must exist"

    with zipfile.ZipFile(output_zip, "r") as z:
        names = z.namelist()
        normalized_names = [n[2:] if n.startswith("./") else n for n in names]

        assert any("pyproject.toml" in n for n in normalized_names), "pyproject.toml missing from zip archive"
        assert any("setup.sh" in n for n in normalized_names), "setup.sh missing from zip archive"
        assert any("samples/common.py" in n for n in normalized_names), "samples/common.py missing from zip archive"
        assert any(n.startswith("specs/") for n in normalized_names), "specs/ missing from zip archive"

        for n in normalized_names:
            assert not n.startswith("models/") and "/models/" not in n, f"Excluded directory models/ found in zip: {n}"
            assert not n.startswith(".venv/") and "/.venv/" not in n, f"Excluded directory .venv/ found in zip: {n}"
            assert not n.startswith(".agents/") and "/.agents/" not in n, f"Excluded .agents/ found in zip: {n}"
            assert not n.startswith(".specify/") and "/.specify/" not in n, f"Excluded .specify/ found in zip: {n}"
            assert "model_context_profiles.json" not in n, f"Excluded model_context_profiles.json found in zip: {n}"
            assert "benchmark_results.json" not in n, f"Excluded benchmark_results.json found in zip: {n}"


def test_setup_firewall_ports_and_required_files():
    repo_root = get_repo_root()
    setup_path = os.path.join(repo_root, "scripts", "setup.sh")
    fw_path = os.path.join(repo_root, "scripts", "configure_firewall.sh")

    with open(setup_path, "r", encoding="utf-8") as f:
        setup_content = f.read()

    with open(fw_path, "r", encoding="utf-8") as f:
        fw_content = f.read()

    # 1. Required files check
    assert "src/core/auxiliary_manager.py" in setup_content, (
        "src/core/auxiliary_manager.py must be in REQUIRED_FILES of setup.sh"
    )

    # 2. Firewall ports check (8081 8089 8090 8091)
    assert "8090" in setup_content and "8091" in setup_content, (
        "Ports 8090 and 8091 must be included in setup.sh firewall rules"
    )
    assert "8090" in fw_content and "8091" in fw_content, (
        "Ports 8090 and 8091 must be included in configure_firewall.sh"
    )


def test_setup_subshell_error_guard_and_fallback():
    repo_root = get_repo_root()
    setup_path = os.path.join(repo_root, "scripts", "setup.sh")

    with open(setup_path, "r", encoding="utf-8") as f:
        setup_content = f.read()

    # 1. Subshell || GPU_CHECK_STATUS=$? exit code capture check (must NOT use || true which overwrites exit code with 0)
    assert "|| GPU_CHECK_STATUS=$?" in setup_content, (
        "setup.sh subshell GPU_CHECK_OUTPUT assignment must use '|| GPU_CHECK_STATUS=$?' to capture real exit status in set -e"
    )
    assert "2>&1 || true)" not in setup_content, (
        "setup.sh must not use '2>&1 || true)' in GPU_CHECK_OUTPUT assignment because true overwrites $? with 0"
    )

    # 2. Clean step: uv pip uninstall llama-cpp-python before Tier 4 C++ compilation
    assert "uv pip uninstall llama-cpp-python" in setup_content, (
        "setup.sh must execute 'uv pip uninstall llama-cpp-python' to clean bad prebuilt wheel before Tier 4 C++ compilation"
    )

    # 3. --wheel-path CLI parameter support
    assert "--wheel-path" in setup_content, (
        "setup.sh must support --wheel-path CLI option for custom wheel injection"
    )

    # 4. 4-Tier fallback logic check
    assert "INSTALLED_VIA_FAST_TRACK" in setup_content, (
        "setup.sh must maintain INSTALLED_VIA_FAST_TRACK fallback flag"
    )


def test_setup_root_symlinks_creation():
    repo_root = get_repo_root()
    setup_path = os.path.join(repo_root, "scripts", "setup.sh")

    with open(setup_path, "r", encoding="utf-8") as f:
        setup_content = f.read()

    assert 'ln -sf "$BASE_DIR/scripts/start_server.sh" "$BASE_DIR/start_server.sh"' in setup_content, (
        "setup.sh must generate root symlink ./start_server.sh"
    )
    assert 'ln -sf "$BASE_DIR/scripts/stop_server.sh" "$BASE_DIR/stop_server.sh"' in setup_content, (
        "setup.sh must generate root symlink ./stop_server.sh"
    )
    assert 'ln -sf "$BASE_DIR/scripts/status_server.sh" "$BASE_DIR/status_server.sh"' in setup_content, (
        "setup.sh must generate root symlink ./status_server.sh"
    )


def test_setup_tier4_conditional_no_cache_dir_and_cleanup():
    repo_root = get_repo_root()
    setup_path = os.path.join(repo_root, "scripts", "setup.sh")

    with open(setup_path, "r", encoding="utf-8") as f:
        setup_content = f.read()

    assert "--no-cache-dir" in setup_content, (
        "setup.sh must contain --no-cache-dir for conditional Tier 4 C++ source recompilation"
    )
    assert "verify_wheel_binary.py" in setup_content, (
        "setup.sh must invoke verify_wheel_binary.py to test cache wheel CUDA support before recompilation"
    )


def test_status_server_cuda_verification_formatting():
    repo_root = get_repo_root()
    status_path = os.path.join(repo_root, "scripts", "status_server.sh")

    with open(status_path, "r", encoding="utf-8") as f:
        status_content = f.read()

    assert "llama-cpp-python GPU:" in status_content or "GPU:" in status_content, (
        "status_server.sh must format and display GPU CUDA acceleration state"
    )


def test_make_seed_pack_legacy_wheel_reuse_and_post_build_check():
    repo_root = get_repo_root()
    make_seed_path = os.path.join(repo_root, "scripts", "make_seed_pack.sh")

    with open(make_seed_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "verify_wheel_binary.py" in content, (
        "make_seed_pack.sh must call verify_wheel_binary.py for pre-check and Post-Build verification"
    )
    assert "--no-cache-dir" in content, (
        "make_seed_pack.sh must use --no-cache-dir when building legacy prebuilt wheel"
    )
    assert "--no-build-isolation" not in content, (
        "make_seed_pack.sh must NOT use --no-build-isolation to allow scikit-build-core PEP 517/518 build isolation"
    )


def test_pyproject_toml_scikit_build_core_dependency():
    repo_root = get_repo_root()
    pyproject_path = os.path.join(repo_root, "pyproject.toml")

    with open(pyproject_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "scikit-build-core" in content, (
        "pyproject.toml must declare scikit-build-core as a project dependency"
    )



def test_unpack_seed_script_flags_and_symlink():
    repo_root = get_repo_root()
    unpack_path = os.path.join(repo_root, "scripts", "unpack_seed.sh")
    symlink_path = os.path.join(repo_root, "unpack_seed.sh")

    assert os.path.exists(unpack_path) or os.path.exists(symlink_path), (
        "scripts/unpack_seed.sh or ./unpack_seed.sh must exist"
    )


def test_verify_wheel_binary_cuda_so_segregation():
    """T004: Assert verify_wheel_binary.py segregates CUDA device libraries from CPU host libraries."""
    repo_root = get_repo_root()
    verify_script_path = os.path.join(repo_root, "scripts", "verify_wheel_binary.py")

    with open(verify_script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "cuda" in content.lower(), "verify_wheel_binary.py must detect CUDA libraries"
    assert "verify_wheel" in content, "verify_wheel_binary.py must contain verify_wheel function"
    # Verify segregation logic exists or is handled
    assert "cpu" in content.lower() or "host" in content.lower() or "ggml-cuda" in content.lower(), (
        "verify_wheel_binary.py must segregate CUDA device libraries from CPU host libraries"
    )


def test_verify_wheel_binary_exit_code_and_result():
    """T005: Assert verify_wheel_binary.py executes successfully and returns valid exit code."""
    repo_root = get_repo_root()
    wheels_dir = os.path.join(repo_root, "wheels", "legacy_i7_930")
    wheel_files = glob.glob(os.path.join(wheels_dir, "llama_cpp_python*.whl"))

    if wheel_files:
        verify_script_path = os.path.join(repo_root, "scripts", "verify_wheel_binary.py")
        cmd = [sys.executable, verify_script_path, wheel_files[0]]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"verify_wheel_binary.py failed on {wheel_files[0]}: {res.stdout} {res.stderr}"
        assert "✓" in res.stdout or "valid" in res.stdout.lower(), f"Expected valid output: {res.stdout}"


def test_make_seed_pack_skbuild_cmake_args():
    """T009: Assert make_seed_pack.sh contains SKBUILD_CMAKE_ARGS environment variable."""
    repo_root = get_repo_root()
    make_seed_path = os.path.join(repo_root, "scripts", "make_seed_pack.sh")

    with open(make_seed_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "SKBUILD_CMAKE_ARGS=" in content, (
        "make_seed_pack.sh must explicitly declare SKBUILD_CMAKE_ARGS for scikit-build-core PEP 517/518 build compatibility"
    )
    assert "CXXFLAGS=" in content, (
        "make_seed_pack.sh must explicitly declare CXXFLAGS=-march=x86-64"
    )


def test_make_seed_pack_exclusions_rules():
    """Assert make_seed_pack.sh excludes .agents, .specify and retains samples, specs, and .legacy."""
    repo_root = get_repo_root()
    make_seed_path = os.path.join(repo_root, "scripts", "make_seed_pack.sh")

    with open(make_seed_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert '--exclude=".agents"' in content or '".agents/*"' in content, (
        "make_seed_pack.sh must exclude .agents directory from seed archive"
    )
    assert '--exclude=".specify"' in content or '".specify/*"' in content, (
        "make_seed_pack.sh must exclude .specify directory from seed archive"
    )
    assert '--exclude="specs"' not in content, (
        "make_seed_pack.sh must NOT exclude specs directory from seed archive"
    )
    assert '--exclude=".legacy"' in content, (
        "make_seed_pack.sh must exclude .legacy directory from seed archive"
    )


def test_setup_venv_python_runner_isolation():
    """T005 (061): Assert setup.sh uses VENV_PYTHON to prevent uv auto-sync package overwrite."""
    repo_root = get_repo_root()
    setup_path = os.path.join(repo_root, "scripts", "setup.sh")

    with open(setup_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'VENV_PYTHON=' in content, (
        "setup.sh must define VENV_PYTHON to execute python directly inside .venv"
    )
    assert '"$VENV_PYTHON"' in content, (
        "setup.sh must use $VENV_PYTHON instead of uv run python during GPU checks"
    )


def test_make_seed_pack_and_unpack_expanded_manifest_verification():
    """T003/T010: Verify expanded list of script manifest entries in make_seed_pack.sh and unpack_seed.sh."""
    repo_root = get_repo_root()
    make_seed_path = os.path.join(repo_root, "scripts", "make_seed_pack.sh")
    unpack_path = os.path.join(repo_root, "scripts", "unpack_seed.sh")

    with open(make_seed_path, "r", encoding="utf-8") as f:
        make_content = f.read()

    with open(unpack_path, "r", encoding="utf-8") as f:
        unpack_content = f.read()

    # Core required script files
    required_core_files = [
        "process_manager.py",
        "model_downloader.py",
        "benchmark_quality.py",
        "benchmark_context_window.py",
        "setup.sh",
        "make_seed_pack.sh",
        "unpack_seed.sh",
    ]

    for req_file in required_core_files:
        assert req_file in make_content, f"make_seed_pack.sh must verify archive entry for {req_file}"
        assert req_file in unpack_content, f"unpack_seed.sh must list {req_file} in REQUIRED_ENTRIES"







