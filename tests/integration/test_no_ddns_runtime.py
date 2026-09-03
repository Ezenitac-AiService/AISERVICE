"""Integration tests for DDNS-free runtime operation (T043)."""
from pathlib import Path
import pytest
from AISERVICE.tests.contract.test_probe_isolation import *

def test_no_duckdns_runtime_cron(aiservice_root: Path):
    """Verify absence of duckdns in any shell startup scripts."""
    for script in [aiservice_root / "run_all_services.sh", aiservice_root / "bootstrap_restore.sh"]:
        if script.exists():
            content = script.read_text(encoding="utf-8")
            assert "duckdns" not in content.lower()
