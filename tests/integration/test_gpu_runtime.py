"""Integration tests for GPU runtime and isolation (T029).

Enforces:
- Docker GPU reservation in docker-compose.yml
- Prohibits direct host port exposure for internal inference endpoints
- Verifies aiservice-probe one-shot container definition
"""

from pathlib import Path
import yaml
import pytest

def test_gpu_service_configuration(repo_root: Path):
    compose_path = repo_root / "AISERVICE" / "docker-compose.yml"
    with open(compose_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    services = config.get("services", {})
    assert "vllm-serv" in services
    vllm = services["vllm-serv"]

    # Internal only: no host ports published
    assert "ports" not in vllm or len(vllm.get("ports", [])) == 0

    # GPU reservation configured
    devices = vllm.get("deploy", {}).get("resources", {}).get("reservations", {}).get("devices", [])
    assert any("gpu" in d.get("capabilities", []) for d in devices)

def test_probe_container_defined(repo_root: Path):
    compose_path = repo_root / "AISERVICE" / "docker-compose.yml"
    with open(compose_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    services = config.get("services", {})
    assert "aiservice-probe" in services
    probe = services["aiservice-probe"]
    assert "aiservice-network" in probe.get("networks", [])
