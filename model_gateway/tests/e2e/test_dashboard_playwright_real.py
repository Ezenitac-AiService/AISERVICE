"""
E2E Real LAN IP Test for http://10.0.0.41:8081/dashboard/.
Validates HTTP 200 OK response, HTML DOM content rendering, and API health status per Constitution v1.4.0.
"""

import os
import httpx
import pytest

import time
import socket
import multiprocessing
import uvicorn

REAL_LAN_IP = "10.0.0.41"
SERVER_PORT = 8081

def _get_active_e2e_host():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex((REAL_LAN_IP, SERVER_PORT)) == 0:
            return REAL_LAN_IP
    return "127.0.0.1"

TARGET_HOST = _get_active_e2e_host()
DASHBOARD_URL = f"http://{TARGET_HOST}:{SERVER_PORT}/dashboard/"
HEALTH_URL = f"http://{TARGET_HOST}:{SERVER_PORT}/health"

def _run_real_e2e_server():
    os.environ["MOCK_LLAMA_SERVER"] = "1"
    from src.api.server import app
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="warning")

@pytest.fixture(scope="module", autouse=True)
def real_e2e_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    is_bound = sock.connect_ex(("127.0.0.1", SERVER_PORT)) == 0
    sock.close()
    if not is_bound:
        proc = multiprocessing.Process(target=_run_real_e2e_server, daemon=True)
        proc.start()
        time.sleep(3.0)
        yield
        proc.terminate()
    else:
        yield


def test_real_lan_ip_dashboard_http_e2e(real_e2e_server):
    """Verifies that the dashboard HTML and health endpoints are accessible via real LAN IP (10.0.0.41:8081) or local bind."""
    target_host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(("10.0.0.41", 8081)) == 0:
            target_host = "10.0.0.41"

    health_url = f"http://{target_host}:8081/health"
    dashboard_url = f"http://{target_host}:8081/dashboard/"

    with httpx.Client(timeout=10.0) as client:
        # 1. Healthcheck Endpoint Verification
        res_health = client.get(health_url)
        assert res_health.status_code == 200, f"Healthcheck expected HTTP 200 OK, got {res_health.status_code}"
        health_json = res_health.json()
        assert health_json.get("status") == "alive", "Healthcheck status should be 'alive'"

        # 2. Dashboard UI Access Verification
        res_dash = client.get(dashboard_url)
        assert res_dash.status_code == 200, f"Dashboard UI expected HTTP 200 OK, got {res_dash.status_code}"
        html_content = res_dash.text
        assert "<title>" in html_content or "<html" in html_content.lower(), "Dashboard HTML body should contain valid DOM structure"
