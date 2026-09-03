"""Contract tests for Native Linux Docker Compose runtime.

Enforces:
- FR-004: Gateway binds 5 entry ports (3000, 8001, 8002, 8003, 8004).
- FR-005: Native Linux Docker & NVIDIA Container Toolkit normalization (no WSL mounts, no /dev/dxg).
- FR-008: Internal components (Model Gateway, Redis, MySQL, backends) NOT published to host.
- Constitution VII: Zero hardcoding, loopback probe prevention, no privileged containers.
"""

from pathlib import Path
import yaml
import pytest

@pytest.fixture
def compose_config(aiservice_root: Path):
    compose_path = aiservice_root / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"
    with open(compose_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def test_no_wsl_artifacts_in_compose(compose_config):
    """Ensure no WSL2 specific paths or devices exist in docker-compose."""
    raw_yaml = yaml.dump(compose_config)
    assert "/dev/dxg" not in raw_yaml, "Found WSL device /dev/dxg in docker-compose.yml"
    assert "/usr/lib/wsl" not in raw_yaml, "Found WSL mount /usr/lib/wsl in docker-compose.yml"
    assert "usr/lib/wsl" not in raw_yaml, "Found WSL library path in docker-compose.yml"

def test_no_privileged_containers(compose_config):
    """Ensure no service runs with privileged: true."""
    services = compose_config.get("services", {})
    for svc_name, svc_cfg in services.items():
        assert not svc_cfg.get("privileged", False), f"Service '{svc_name}' must not have privileged: true"

def test_internal_ports_not_published_to_host(compose_config):
    """Internal components (Model Gateway, Redis, MySQL, backend services) must NOT expose ports to host."""
    services = compose_config.get("services", {})
    internal_services = ["vllm-serv", "redis", "bteam_db", "pilos-db", "oliview_backend", "pilos_web", "oliview_frontend", "oliview_chatbot_a", "oliview_chatbot_b"]
    for svc_name in internal_services:
        if svc_name in services:
            ports = services[svc_name].get("ports", [])
            assert not ports, f"Internal service '{svc_name}' must not publish host ports. Found: {ports}"

def test_gateway_publishes_five_tunnel_ports(compose_config):
    """Gateway service must publish the 5 required tunnel alias ports: 3000, 8001, 8002, 8003, 8004."""
    services = compose_config.get("services", {})
    assert "gateway" in services, "Service 'gateway' must exist in docker-compose.yml"
    ports = services["gateway"].get("ports", [])
    expected_ports = ["3000", "8001", "8002", "8003", "8004"]
    ports_str = " ".join(str(p) for p in ports)
    for p in expected_ports:
        assert p in ports_str, f"Gateway missing expected port mapping for {p}. Found: {ports}"

def test_gpu_services_use_device_reservation(compose_config):
    """GPU accelerated services must use standard NVIDIA device reservation."""
    services = compose_config.get("services", {})
    vllm_svc = services.get("vllm-serv")
    assert vllm_svc is not None, "Service 'vllm-serv' must exist"
    deploy = vllm_svc.get("deploy", {})
    resources = deploy.get("resources", {})
    reservations = resources.get("reservations", {})
    devices = reservations.get("devices", [])
    assert len(devices) > 0, "vllm-serv must configure deploy.resources.reservations.devices for NVIDIA GPU"
    has_gpu = any("gpu" in d.get("capabilities", []) for d in devices)
    assert has_gpu, "vllm-serv devices must specify 'gpu' capability"

def test_no_loopback_healthcheck_in_vllm_serv(compose_config):
    """vllm-serv must not probe itself via loopback in healthcheck."""
    services = compose_config.get("services", {})
    vllm_svc = services.get("vllm-serv", {})
    healthcheck = vllm_svc.get("healthcheck", {})
    if healthcheck:
        test_cmd = " ".join(healthcheck.get("test", []))
        assert "127.0.0.1" not in test_cmd and "localhost" not in test_cmd, (
            "vllm-serv must not use loopback healthcheck (Constitution VII). "
            "Use aiservice-probe container instead."
        )
