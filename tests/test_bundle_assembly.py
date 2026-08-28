# -*- coding: utf-8 -*-
"""
tests/test_bundle_assembly.py
=============================
User Story 4: 클린 소스 번들링 및 실사용 .env 보존 테스트.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from make_migration_pack import should_exclude_path, EXCLUDE_PATTERNS


def test_exclusion_filters():
    assert should_exclude_path(Path(".git"), ROOT_DIR) is True
    assert should_exclude_path(Path(".venv"), ROOT_DIR) is True
    assert should_exclude_path(Path("node_modules"), ROOT_DIR) is True
    assert should_exclude_path(Path("__pycache__"), ROOT_DIR) is True
    assert should_exclude_path(Path("dist"), ROOT_DIR) is True
    assert should_exclude_path(Path(".pytest_cache"), ROOT_DIR) is True


def test_env_inclusion():
    # .env and ddns/.env must NOT be excluded
    assert should_exclude_path(Path(".env"), ROOT_DIR) is False
    assert should_exclude_path(Path("ddns/.env"), ROOT_DIR) is False
    assert should_exclude_path(Path("docker-compose.yml"), ROOT_DIR) is False
    assert should_exclude_path(Path("migration_pack/scripts/bootstrap_restore.sh"), ROOT_DIR) is False
