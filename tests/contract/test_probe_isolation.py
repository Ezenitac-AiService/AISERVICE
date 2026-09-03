"""Contract tests for internal probe network isolation and loopback elimination (T043).

Enforces:
- Constitution VII: Prohibition of loopback dependencies.
- Probe container: aiservice-probe executes inside aiservice-network using container DNS names.
- Zero reliance on 127.0.0.1 host loopback for health verification.
"""

from pathlib import Path
import re
import pytest

def test_verify_script_does_not_probe_host_loopback(aiservice_root: Path):
    """verify_migration.py must not hardcode 127.0.0.1 for internal component checks."""
    verify_script = aiservice_root / "migration_pack" / "scripts" / "verify_migration.py"
    if verify_script.exists():
        content = verify_script.read_text(encoding="utf-8")
        # Ensure internal service checks (model gateway, redis, db) do not use 127.0.0.1
        lines = content.splitlines()
        for line in lines:
            if any(svc in line for svc in ["8081", "8090", "8091", "6379", "3306"]):
                assert "127.0.0.1" not in line and "localhost" not in line, (
                    f"Found prohibited loopback probe on internal service in line: {line}"
                )

def test_probe_shell_script_uses_internal_dns(aiservice_root: Path):
    """probe_endpoints.sh must target container hostnames in aiservice-network."""
    probe_script = aiservice_root / "scripts" / "probe_endpoints.sh"
    if probe_script.exists():
        content = probe_script.read_text(encoding="utf-8")
        assert "vllm-serv-gateway" in content or "gateway" in content
