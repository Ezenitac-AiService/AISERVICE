# -*- coding: utf-8 -*-
"""
tests/test_volume_export.py
===========================
User Story 3: 볼륨 백업 및 Mutex 복원 로직 단위 테스트.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from migration_pack.scripts.export_docker_volumes import get_managed_volumes_map


def test_managed_volumes_map():
    vol_map = get_managed_volumes_map()
    assert "ateam_db_data" in vol_map
    assert "bteam_bteam_mysql_data" in vol_map or "bteam_mysql_data" in vol_map
    assert "aiservice_redis_data" in vol_map or "redis_data" in vol_map
    assert "green_chroma_data" in vol_map or "bteam-green_green_chroma_data" in vol_map
