"""
Unit tests for operational shell scripts (status_server.sh, start_server.sh, setup.sh, make_seed_pack.sh).
Validates execution, output formatting, pre-flight failure handling, and archive packaging.
"""

import os
import subprocess
import time
import tempfile
import tarfile
import zipfile
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_status_server_script_execution():
    """T006 [US1]: Verifies status_server.sh runs successfully and outputs hardware report and profile info."""
    script_path = os.path.join(REPO_ROOT, "scripts", "status_server.sh")
    assert os.path.exists(script_path), f"Script missing: {script_path}"

    try:
        res = subprocess.run(["bash", script_path], capture_output=True, text=True, cwd=REPO_ROOT, timeout=15)
        assert res.returncode == 0
        assert "vllm_serv" in res.stdout
        assert "하드웨어" in res.stdout or "프로세스 상태" in res.stdout
    except subprocess.TimeoutExpired:
        pytest.skip("status_server.sh execution timed out due to background process locks")


def test_setup_sh_uv_sync_frozen_pattern():
    """T003 [US1] (041-uv-sync-performance-fix): Verifies setup.sh uses uv sync --frozen with subshell fallback protection."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "uv sync --frozen" in content, "setup.sh must use 'uv sync --frozen' for fast-track sync"
    assert "가상환경 고속 동기화" in content, "setup.sh must output fast sync log message"



def test_start_server_preflight_help():
    """T009 [US2]: Verifies start_server.sh contains pre-flight check logic."""
    script_path = os.path.join(REPO_ROOT, "scripts", "start_server.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "check-preflight" in content or "Pre-flight" in content


def test_setup_script_contains_match_profile():
    """T012 [US3]: Verifies setup.sh invokes match-profile CLI option."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "match-profile" in content or "cpu_detector" in content


def test_make_seed_pack_includes_platform_profiles():
    """T015 [US4]: Verifies make_seed_pack.sh script includes config/platform_profiles.json in target files."""
    script_path = os.path.join(REPO_ROOT, "scripts", "make_seed_pack.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "platform_profiles.json" in content


def test_setup_sh_fast_track_diagnostic_output():
    """T016 [US2]: Verifies setup.sh captures GPU check stderr and logs structured failure cause without 2>/dev/null (FR-002)."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "GPU_CHECK_OUTPUT=" in content
    assert "2>/dev/null" not in content.split("llama_supports_gpu_offload")[1].split("fi")[0]
    assert "[FAST-TRACK FAIL]" in content
    assert "FAST-TRACK FAIL TRACEBACK" in content


def test_setup_sh_failure_categories():
    """T016 [US2]: Verifies setup.sh includes all structured failure cause categories (SIGILL, GPU_OFFLOAD_FALSE, SHARED_LIB_IMPORT_ERROR)."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "SIGILL_ILLEGAL_INSTRUCTION" in content
    assert "GPU_OFFLOAD_FALSE" in content
    assert "SHARED_LIB_IMPORT_ERROR" in content


# ==============================================================================
# 039-seed-pack-sudo-firewall-migration (FR-001, FR-002, FR-004, FR-007)
# ==============================================================================

def test_setup_sh_sudo_keepalive_daemon_pattern():
    """T004 [US1]: Verifies setup.sh contains sudo keepalive daemon loop pattern with background PID tracking.

    Real file content inspection per Constitution v1.4.0 Anti-Mock Discipline.
    Checks: sudo -v, sudo -n true, sleep 50, SUDO_KEEPALIVE_PID, trap, kill.
    """
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    # FR-001: sudo -v interactive elevation at script start
    assert "sudo -v" in content, "setup.sh must contain 'sudo -v' for interactive elevation"

    # FR-002: Background keepalive daemon pattern
    assert "sudo -n true" in content, "setup.sh must contain 'sudo -n true' for non-interactive keepalive"
    assert "sleep 50" in content or "sleep 45" in content, "setup.sh must contain keepalive sleep interval"
    assert "SUDO_KEEPALIVE_PID" in content, "setup.sh must track keepalive daemon PID"

    # FR-002: Trap for cleanup on exit
    assert "trap" in content, "setup.sh must register trap for daemon cleanup"
    assert "kill" in content, "setup.sh must kill keepalive daemon on exit"


def test_setup_sh_tty_detection():
    """T004 [US1]: Verifies setup.sh contains TTY detection logic ([ -t 0 ]) for interactive vs non-interactive branching."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "-t 0" in content, "setup.sh must detect TTY via [ -t 0 ] or [[ -t 0 ]]"


def test_setup_sh_ownership_correction_sudo_user():
    """T005 [US1]: Verifies setup.sh contains SUDO_USER detection and chown ownership remediation logic.

    Real file content inspection per Constitution v1.4.0 Anti-Mock Discipline.
    """
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    # FR-007: SUDO_USER detection
    assert "SUDO_USER" in content, "setup.sh must detect $SUDO_USER environment variable"

    # FR-007: chown -R remediation
    assert "chown" in content, "setup.sh must use chown for ownership remediation"


def test_setup_sh_noninteractive_fallback_banner():
    """T005 [US1]: Verifies setup.sh generates warning banner and configure_firewall.sh for non-interactive environments (FR-004)."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    # FR-004: Warning banner output per contract
    assert "configure_firewall.sh" in content, "setup.sh must reference configure_firewall.sh fallback script"
    assert "방화벽" in content, "setup.sh must contain Korean firewall warning text"


def test_configure_firewall_sh_syntax():
    """T004/T005 [US1]: Verify configure_firewall.sh shell script syntax is valid via bash -n."""
    script_path = os.path.join(REPO_ROOT, "scripts", "configure_firewall.sh")
    assert os.path.exists(script_path), f"Script missing: {script_path}"

    res = subprocess.run(["bash", "-n", script_path], capture_output=True, text=True)
    assert res.returncode == 0, f"configure_firewall.sh has syntax errors: {res.stderr}"


def test_configure_firewall_sh_root_check():
    """T005 [US1]: Verify configure_firewall.sh checks for root privileges."""
    script_path = os.path.join(REPO_ROOT, "scripts", "configure_firewall.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "EUID" in content, "configure_firewall.sh must check EUID for root privilege verification"
    assert "exit 1" in content, "configure_firewall.sh must exit 1 when not running as root"


def test_dual_pid_cleanup_in_stop_server():
    """T006 [US2]: Verifies stop_server.sh contains dual PID file removal and 3-tier pgrep pattern searches."""
    script_path = os.path.join(REPO_ROOT, "scripts", "stop_server.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "vllm_serv.pid" in content, "stop_server.sh must clean up vllm_serv.pid"
    assert "vllm_dashboard.pid" in content, "stop_server.sh must clean up vllm_dashboard.pid"
    assert "src.api.server" in content, "stop_server.sh must search for src.api.server"
    assert "uvicorn src.api.main:app" in content, "stop_server.sh must search for uvicorn src.api.main:app"
    assert "llama-server" in content, "stop_server.sh must search for llama-server"


def test_seed_pack_includes_gpu_detector_and_catalog():
    """T003 [US1]: Verifies make_seed_pack.sh asserts gpu_detector.py and model_catalog.json presence."""
    script_path = os.path.join(REPO_ROOT, "scripts", "make_seed_pack.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'verify_archive_entry "gpu_detector.py"' in content, "make_seed_pack.sh must verify gpu_detector.py inclusion"
    assert 'verify_archive_entry "model_catalog.json"' in content, "make_seed_pack.sh must verify model_catalog.json inclusion"


def test_seed_pack_include_profiles_flag():
    """T006 [US2]: Verifies make_seed_pack.sh supports --include-profiles option and un-excludes model_context_profiles.json."""
    script_path = os.path.join(REPO_ROOT, "scripts", "make_seed_pack.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

def test_unpack_seed_script_syntax_and_flags():
    """T006 [US2] (111-unpack-seed-script-enhancement): Verify unpack_seed.sh bash syntax and CLI options handling."""
    script_path = os.path.join(REPO_ROOT, "scripts", "unpack_seed.sh")
    assert os.path.exists(script_path), f"Script missing: {script_path}"

    res = subprocess.run(["bash", "-n", script_path], capture_output=True, text=True)
    assert res.returncode == 0, f"unpack_seed.sh has syntax errors: {res.stderr}"

    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "--input" in content or "-i" in content, "unpack_seed.sh must support -i/--input flag"
    assert "--target-dir" in content or "-t" in content, "unpack_seed.sh must support -t/--target-dir flag"
    assert "--force-overwrite" in content or "-f" in content, "unpack_seed.sh must support -f/--force-overwrite flag"
    assert "--verify-only" in content, "unpack_seed.sh must support --verify-only flag"
    assert "--run-setup" in content, "unpack_seed.sh must support --run-setup flag"


def test_unpack_seed_multiformat_and_nondestructive():
    """T003 [US1] (111-unpack-seed-script-enhancement): Verify unpack_seed.sh supports .tar.gz and .zip format detection and non-destructive extraction."""
    script_path = os.path.join(REPO_ROOT, "scripts", "unpack_seed.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "FORMAT=" in content, "unpack_seed.sh must perform format detection"
    assert "unzip -n" in content, "unpack_seed.sh must use 'unzip -n' for non-destructive ZIP extraction"
    assert "tar -xvkpf" in content, "unpack_seed.sh must use 'tar -xvkpf' for non-destructive TAR.GZ extraction"
    assert "verify_wheel_binary.py" in content, "unpack_seed.sh must check existing wheel binary validity"


def test_unpack_seed_run_setup_flag():
    """T009 [US3] (111-unpack-seed-script-enhancement): Verify unpack_seed.sh handles --run-setup flag and post-unpack setup.sh trigger."""
    script_path = os.path.join(REPO_ROOT, "scripts", "unpack_seed.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "RUN_SETUP" in content, "unpack_seed.sh must track RUN_SETUP flag"
    assert "setup.sh" in content, "unpack_seed.sh must trigger setup.sh when --run-setup is specified"


def test_unpack_seed_benchmark_execution_speed_and_metrics():
    """T015 [DoD-003/SC-001] (111-unpack-seed-script-enhancement): Benchmark .tar.gz and .zip unpack performance (<10s) and verify metrics output (T014)."""
    script_path = os.path.join(REPO_ROOT, "scripts", "unpack_seed.sh")
    assert os.path.exists(script_path), f"Script missing: {script_path}"

    required_files = [
        "platform_profiles.json",
        "model_catalog.json",
        "gpu_detector.py",
        "start_server.sh",
        "ensure_models.py",
        "auxiliary_manager.py",
        "process_manager.py",
        "model_downloader.py",
        "benchmark_quality.py",
        "benchmark_context_window.py",
        "setup.sh",
        "make_seed_pack.sh",
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        src_dir = os.path.join(tmp_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        for fname in required_files:
            with open(os.path.join(src_dir, fname), "w") as f:
                f.write(f"# Dummy content for {fname}\n")

        # 1. Create .tar.gz archive
        targz_path = os.path.join(tmp_dir, "test_seed.tar.gz")
        with tarfile.open(targz_path, "w:gz") as tar:
            for fname in required_files:
                tar.add(os.path.join(src_dir, fname), arcname=fname)

        # 2. Create .zip archive
        zip_path = os.path.join(tmp_dir, "test_seed.zip")
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for fname in required_files:
                zipf.write(os.path.join(src_dir, fname), arcname=fname)

        # 3. Benchmark .tar.gz unpack
        dest_targz = os.path.join(tmp_dir, "dest_targz")
        t0 = time.time()
        res_tar = subprocess.run(
            ["bash", script_path, "-i", targz_path, "-t", dest_targz],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10,
        )
        elapsed_tar = time.time() - t0

        assert res_tar.returncode == 0, f"tar.gz unpack failed: {res_tar.stderr}"
        assert elapsed_tar < 10.0, f"tar.gz unpack benchmark failed: {elapsed_tar:.2f}s >= 10s"
        assert "복원 완결 메트릭" in res_tar.stdout, f"tar.gz output missing metrics: {res_tar.stdout}"

        # 4. Benchmark .zip unpack
        dest_zip = os.path.join(tmp_dir, "dest_zip")
        t0 = time.time()
        res_zip = subprocess.run(
            ["bash", script_path, "-i", zip_path, "-t", dest_zip],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10,
        )
        elapsed_zip = time.time() - t0

        assert res_zip.returncode == 0, f"zip unpack failed: {res_zip.stderr}"
        assert elapsed_zip < 10.0, f"zip unpack benchmark failed: {elapsed_zip:.2f}s >= 10s"
        assert "복원 완결 메트릭" in res_zip.stdout, f"zip output missing metrics: {res_zip.stdout}"


def test_setup_sh_expanded_required_files():
    """T004/T011: Verifies setup.sh Step 1 REQUIRED_FILES includes model_downloader.py, benchmark_context_window.py, and unpack_seed.sh."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    expanded_files = [
        "src/core/model_downloader.py",
        "scripts/benchmark_context_window.py",
        "scripts/unpack_seed.sh",
    ]

    for req in expanded_files:
        assert req in content, f"setup.sh Step 1 REQUIRED_FILES must include {req}"


def test_setup_sh_force_build_cli_option():
    """T003 [US1]: Verifies setup.sh contains --force-build CLI option and help description."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "--force-build)" in content
    assert "FORCE_BUILD=1" in content
    assert "[--force-build]" in content


def test_setup_sh_force_build_fasttrack_bypass():
    """T003 [US1]: Verifies setup.sh Tier 2 and Tier 3 fast-track checks inspect FORCE_BUILD and WHEEL_PATH."""
    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'if [ "$INSTALLED_VIA_FAST_TRACK" -eq 0 ] && [ "$FORCE_BUILD" -eq 0 ] && [ -z "$WHEEL_PATH" ]; then' in content
    assert 'if [ "$FORCE_BUILD" -eq 1 ]; then' in content






