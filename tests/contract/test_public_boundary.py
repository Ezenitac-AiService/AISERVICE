"""Contract tests for public web boundary and internal service isolation.

Enforces:
- FR-008: Gateway web routes are public; Model Gateway, Redis, DB, internal APIs are isolated in private network.
- SC-006: 0 direct external access routes to internal service ports.
"""

from pathlib import Path
import yaml
import pytest

def test_compose_exposes_only_gateway(aiservice_root: Path):
    compose_path = aiservice_root / "docker-compose.yml"
    with open(compose_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    services = config.get("services", {})
    for svc_name, svc_cfg in services.items():
        ports = svc_cfg.get("ports", [])
        if svc_name == "gateway":
            assert len(ports) > 0, "Gateway must expose entry ports"
        else:
            assert len(ports) == 0, f"Internal service '{svc_name}' must NOT expose ports to host. Found: {ports}"

def test_nginx_config_does_not_expose_internal_endpoints(aiservice_root: Path):
    template_path = aiservice_root / "gateway" / "nginx.conf.template"
    content = template_path.read_text(encoding="utf-8")

    # Check that database ports (3306) and redis (6379) are not in upstream or proxy_pass targets
    assert "3306" not in content, "Database port 3306 must not appear in Nginx configuration"
    assert "6379" not in content, "Redis port 6379 must not appear in Nginx configuration"

    # Model gateway internal ports (8081, 8090, 8091) should not have direct public location mappings
    assert "location /v1/models" not in content, "Model gateway internal API must not have direct public location"
    assert "location /v1/chat/completions" not in content, "Raw LLM completions must not be directly exposed publicly"
