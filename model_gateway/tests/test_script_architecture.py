"""
Unit & Integration tests for scripts architecture, modularity, and decoupling (093-refactor-scripts-architecture).
FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008.
"""

import os
import sys
import subprocess
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")


def test_scripts_directory_exists_and_files():
    """T005: scripts/ 디렉토리 내 스크립트 파일 존재 검증."""
    assert os.path.isdir(SCRIPTS_DIR)
    common_sh = os.path.join(SCRIPTS_DIR, "common.sh")
    assert os.path.isfile(common_sh)


def test_common_sh_mixins_exist():
    """T005: common.sh 믹스인 함수 존재 정적 검증 (try_optional_step, get_configured_port)."""
    common_sh = os.path.join(SCRIPTS_DIR, "common.sh")
    with open(common_sh, "r", encoding="utf-8") as f:
        content = f.read()

    assert "try_optional_step()" in content
    assert "get_configured_port()" in content


def test_get_configured_port_execution():
    """T004: common.sh get_configured_port 실행 검증."""
    cmd = [
        "bash", "-c",
        f"source {os.path.join(SCRIPTS_DIR, 'common.sh')} && get_configured_port main"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.stdout.strip().isdigit()
    assert int(proc.stdout.strip()) in [8081, 8082, 8090, 8091]


def test_try_optional_step_execution():
    """T003: common.sh try_optional_step 실행 검증."""
    cmd = [
        "bash", "-c",
        f"source {os.path.join(SCRIPTS_DIR, 'common.sh')} && try_optional_step 'TrueTest' true"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "정상 완수" in proc.stdout or "성공" in proc.stdout


def test_setup_sh_syntax_and_dryrun():
    """T008, T010: setup.sh 구문 정합성 및 --help 작동 검증."""
    cmd = ["bash", "scripts/setup.sh", "--help"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)
    assert proc.returncode == 0
    assert "Usage" in proc.stdout
