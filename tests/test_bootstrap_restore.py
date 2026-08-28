# -*- coding: utf-8 -*-
"""
tests/test_bootstrap_restore.py
===============================
User Story 5: bootstrap_restore.sh 진입점 및 복원 파이프라인 테스트.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest


def test_bootstrap_restore_script_structure():
    script_path = ROOT_DIR / "migration_pack" / "scripts" / "bootstrap_restore.sh"
    assert script_path.is_file()

    content = script_path.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content
    assert "install_prerequisites.sh" in content
    assert "normalize_compose.py" in content
    assert "bootstrap_restore.py" in content
    assert "chmod 600" in content
    assert "duck.sh" in content
    assert "verify_migration.py" in content
