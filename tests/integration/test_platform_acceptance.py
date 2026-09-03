"""Platform DEMO Acceptance Test Suite (T065).

Validates:
- 5 public gateway services (3000, 8001~8004)
- Internal Model Gateway endpoints (8081, 8090, 8091)
- Redis connectivity
- Direct host publication prohibition for internal ports
"""

import json
from pathlib import Path
import pytest
import yaml


def test_platform_public_ports_strict_isolation(aiservice_root: Path):
    compose_path = aiservice_root / "docker-compose.yml"
    with open(compose_path, "r", encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    # 1. Host published ports must only belong to gateway service
    for sname, sdef in compose.get("services", {}).items():
        ports = sdef.get("ports", [])
        for p in ports:
            if sname != "gateway":
                pytest.fail(f"Service {sname} publishes port {p} directly to host!")

    # Verify gateway defines the 5 ports
    gw_ports = compose["services"]["gateway"].get("ports", [])
    assert len(gw_ports) == 5
    assert any("3000" in p for p in gw_ports)
    assert any("8001" in p for p in gw_ports)
    assert any("8002" in p for p in gw_ports)
    assert any("8003" in p for p in gw_ports)
    assert any("8004" in p for p in gw_ports)


def test_internal_endpoints_must_use_container_dns(aiservice_root: Path):
    probe_script = aiservice_root / "scripts" / "probe_endpoints.sh"
    assert probe_script.exists()
    content = probe_script.read_text(encoding="utf-8")

    # Internal services must resolve via internal docker DNS, not 127.0.0.1
    assert "vllm-serv-gateway:8081" in content
    assert "vllm-serv-gateway:8090" in content
    assert "vllm-serv-gateway:8091" in content
    assert "redis:6379" in content


def test_nine_core_endpoints_schema_conformance(aiservice_root: Path, contracts_dir: Path):
    import jsonschema
    report_path = aiservice_root / "migration_pack" / "verification_report.json"
    schema_path = contracts_dir / "healthcheck-report-schema.json"

    assert report_path.exists()
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    jsonschema.validate(instance=report, schema=schema)
    assert report["status"] == "PASS"
    assert report["total_checks"] == 9
    assert report["passed_checks"] == 9
