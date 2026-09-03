"""Contract tests for complete removal of DuckDNS artifacts and scripts (T041).

Enforces:
- FR-010: Complete removal of DuckDNS cron, duck.sh, and external DDNS update network traffic.
- SC-004: Zero external DDNS dependencies in runtime templates and scripts.
"""

from pathlib import Path
import re
import pytest

def test_no_duckdns_in_compose(aiservice_root: Path):
    compose_path = aiservice_root / "docker-compose.yml"
    content = compose_path.read_text(encoding="utf-8")
    assert "duckdns" not in content.lower()
    assert "duck.sh" not in content.lower()

def test_no_duckdns_in_env_example(aiservice_root: Path):
    env_example = aiservice_root / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    assert "DUCKDNS" not in content
    assert "duckdns" not in content.lower()

def test_no_duckdns_in_migration_template(aiservice_root: Path):
    template = aiservice_root / "migration_pack" / "config" / ".env.migration.template"
    content = template.read_text(encoding="utf-8")
    assert "DUCKDNS" not in content
    assert "duckdns" not in content.lower()

def test_no_duck_sh_in_gateway(aiservice_root: Path):
    gateway_dir = aiservice_root / "gateway"
    assert not (gateway_dir / "duck.sh").exists()
