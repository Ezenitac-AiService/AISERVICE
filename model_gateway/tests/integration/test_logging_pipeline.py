"""
E2E Integration test for Client Access Logging and API Key Management Pipeline.
"""

import os
import pytest
from fastapi.testclient import TestClient
from src.api.server import create_app
from src.core.config_manager import ConfigManager
from src.core.api_key_manager import get_api_key_manager
from src.core.client_logger import get_client_logger


@pytest.fixture
def e2e_client(tmp_path):
    log_dir = str(tmp_path / "logs")
    config_path = str(tmp_path / "server_config.json")

    cm = ConfigManager(config_path=config_path)
    cm.invalidate_all_caches()
    cm._write_atomic_server_config(cm.get_server_config(), admin_secret="admin_e2e_secret", api_key_enabled=True)

    key_mgr = get_api_key_manager()
    key_mgr.config_path = config_path

    logger_mgr = get_client_logger()
    logger_mgr.log_dir = log_dir

    app = create_app()
    with TestClient(app) as client:
        yield client, key_mgr, log_dir

    cm._write_atomic_server_config(cm.get_server_config(), api_key_enabled=False)
    cm.invalidate_all_caches()




def test_e2e_logging_and_api_key_flow(e2e_client):
    client, key_mgr, log_dir = e2e_client

    # 1. Unauthenticated Request -> Should return 401
    res_unauth = client.post(
        "/v1/chat/completions",
        json={"model": "qwen3.5-4b", "messages": [{"role": "user", "content": "test"}]}
    )
    assert res_unauth.status_code == 401
    assert "X-Request-ID" in res_unauth.headers

    # 2. Generate API Key via Admin Endpoint
    res_gen = client.post(
        "/v1/admin/api-keys",
        json={"name": "E2E-Test-App"},
        headers={"X-Admin-Secret": "admin_e2e_secret"}
    )
    assert res_gen.status_code == 201
    raw_key = res_gen.json()["raw_api_key"]
    masked_key = res_gen.json()["masked_key"]

    # 3. Authenticated Request with valid Bearer Token -> Should return 200/503 depending on model load state
    res_auth = client.post(
        "/v1/chat/completions",
        json={"model": "qwen3.5-4b", "messages": [{"role": "user", "content": "Hello"}], "user": "e2e-user-1"},
        headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert "X-Request-ID" in res_auth.headers

    # 4. Check Health Liveness (Public Endpoint) -> 200 OK
    res_health = client.get("/health/liveness")
    assert res_health.status_code == 200
    assert "X-Request-ID" in res_health.headers
