import pytest
from fastapi.testclient import TestClient
from src.api.server import create_app


def test_subnet_middleware_allowed_client():
    app = create_app()
    with TestClient(app) as client:
        # TestClient requests have client.host = "testclient"
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


def test_subnet_middleware_192_168_0_x_access_allowed():
    """FR-001 [US1]: Verifies 192.168.0.x and 10.0.x.x private LAN clients return HTTP 200 OK."""
    from src.api.middleware.subnet_filter import IpSubnetGuard
    guard = IpSubnetGuard(["127.0.0.1", "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"])

    assert guard.is_allowed("192.168.0.15") is True
    assert guard.is_allowed("192.168.0.100") is True
    assert guard.is_allowed("10.0.1.20") is True
    assert guard.is_allowed("172.16.0.5") is True
    assert guard.is_allowed("127.0.0.1") is True
    assert guard.is_allowed("localhost") is True


def test_subnet_middleware_blocks_external_public_ip():
    """FR-001 [US1]: Verifies public external IP addresses are denied (False)."""
    from src.api.middleware.subnet_filter import IpSubnetGuard
    guard = IpSubnetGuard(["127.0.0.1", "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"])

    assert guard.is_allowed("203.0.113.5") is False
    assert guard.is_allowed("8.8.8.8") is False
    assert guard.is_allowed("1.1.1.1") is False

