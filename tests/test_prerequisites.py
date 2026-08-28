# -*- coding: utf-8 -*-
"""
tests/test_prerequisites.py
===========================
User Story 1: 클린 Ubuntu 24.04 LTS 환경 사전 요구사항 감지 및 스크립트 검증.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest


def test_install_prerequisites_script_structure():
    script_path = ROOT_DIR / "migration_pack" / "scripts" / "install_prerequisites.sh"
    assert script_path.is_file(), "install_prerequisites.sh script must exist"

    content = script_path.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content
    assert "DEBIAN_FRONTEND=noninteractive" in content
    assert "download.docker.com" in content
    assert "nvidia-container-toolkit" in content
    assert "nvidia-ctk runtime configure --runtime=docker" in content
    assert "snap" in content  # Snap Docker detection guardrail
    assert "python-is-python3" in content or "python3" in content
