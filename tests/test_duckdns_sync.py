# -*- coding: utf-8 -*-
"""
tests/test_duckdns_sync.py
==========================
User Story 6: DuckDNS IPv4 갱신 및 크론 등록 테스트.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest


def test_duck_sh_script():
    duck_sh = ROOT_DIR / "ddns" / "duck.sh"
    assert duck_sh.is_file()

    content = duck_sh.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content
    assert "curl -4" in content
    assert "https://www.duckdns.org/update" in content
    assert "OK" in content
    assert "duckdns.log" in content
