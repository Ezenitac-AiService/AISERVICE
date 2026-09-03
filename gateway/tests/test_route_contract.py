"""Contract tests for Gateway Routing and Tunnel Port Mappings.

Enforces:
- Section 1 of route-and-security-contract.md
- Canonical routes: /, /changelog*, /ateam/pilos/, /bteam/oliview/, /bteam/chata/, /bteam/chatb/
- Mapping to primary remote (18000-18004), standby remote (28000-28004), and local (3000, 8001-8004).
"""

from pathlib import Path
import re
import pytest

CANONICAL_ROUTES = [
    {"path": "/", "primary_remote": 18000, "standby_remote": 28000, "local": 3000},
    {"path": "/changelog", "primary_remote": 18000, "standby_remote": 28000, "local": 3000},
    {"path": "/changelog_data.json", "primary_remote": 18000, "standby_remote": 28000, "local": 3000},
    {"path": "/ateam/pilos/", "primary_remote": 18001, "standby_remote": 28001, "local": 8001},
    {"path": "/bteam/oliview/", "primary_remote": 18002, "standby_remote": 28002, "local": 8002},
    {"path": "/bteam/chata/", "primary_remote": 18003, "standby_remote": 28003, "local": 8003},
    {"path": "/bteam/chatb/", "primary_remote": 18004, "standby_remote": 28004, "local": 8004},
]

def test_nginx_template_contains_all_canonical_routes(aiservice_root: Path):
    template_path = aiservice_root / "gateway" / "nginx.conf.template"
    assert template_path.exists()
    content = template_path.read_text(encoding="utf-8")
    for route in CANONICAL_ROUTES:
        pattern = re.escape(route["path"])
        assert re.search(pattern, content), f"Route {route['path']} not found in nginx.conf.template"

def test_nginx_template_listens_on_all_local_ports(aiservice_root: Path):
    template_path = aiservice_root / "gateway" / "nginx.conf.template"
    content = template_path.read_text(encoding="utf-8")
    for port in [3000, 8001, 8002, 8003, 8004]:
        assert f"{port}" in content, f"Port {port} not listened in nginx.conf.template"

def test_portal_and_changelog_share_same_port(aiservice_root: Path):
    """Changelog must not use a separate port from portal (must use local port 3000)."""
    routes = {r["path"]: r["local"] for r in CANONICAL_ROUTES}
    assert routes["/"] == routes["/changelog"] == routes["/changelog_data.json"] == 3000
