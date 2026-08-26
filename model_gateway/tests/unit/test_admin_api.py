"""
Unit & Contract tests for Admin API endpoints (/v1/admin/*).
"""

import pytest
from fastapi.testclient import TestClient
from src.api.server import create_app
from src.core.config_manager import ConfigManager
from src.core.api_key_manager import get_api_key_manager


@pytest.fixture
def client(tmp_path, monkeypatch):
    config_path = str(tmp_path / "server_config.json")
    cm = ConfigManager(config_path=config_path)
    cm.invalidate_all_caches()
    cm._write_atomic_server_config(cm.get_server_config(), admin_secret="test_admin_secret_123")

    key_mgr = get_api_key_manager()
    key_mgr.config_path = config_path

    async def mock_unload():
        pass
    monkeypatch.setattr("src.api.server.llama_manager.unload_model", mock_unload)

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    key_mgr.config_path = "config/server_config.json"
    cm.invalidate_all_caches()






def test_admin_login(client):
    # Success Login
    res = client.post("/v1/admin/auth/login", json={"admin_secret": "test_admin_secret_123"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Failed Login
    res_failed = client.post("/v1/admin/auth/login", json={"admin_secret": "wrong_secret"})
    assert res_failed.status_code == 401


def test_admin_api_keys_crud(client):
    # 1. Unauthorized Access (403)
    res_unauth = client.get("/v1/admin/api-keys")
    assert res_unauth.status_code == 403

    # 2. Create Key with Header
    res_create = client.post(
        "/v1/admin/api-keys",
        json={"name": "Client-App-1"},
        headers={"X-Admin-Secret": "test_admin_secret_123"}
    )
    assert res_create.status_code == 201
    data = res_create.json()
    assert "raw_api_key" in data
    assert data["raw_api_key"].startswith("sk-vllm-")
    key_id = data["key_id"]

    # 3. List Keys
    res_list = client.get(
        "/v1/admin/api-keys",
        headers={"X-Admin-Secret": "test_admin_secret_123"}
    )
    assert res_list.status_code == 200
    keys = res_list.json()["api_keys"]
    assert len(keys) == 1
    assert keys[0]["key_id"] == key_id

    # 4. Delete Key
    res_delete = client.delete(
        f"/v1/admin/api-keys/{key_id}",
        headers={"X-Admin-Secret": "test_admin_secret_123"}
    )
    assert res_delete.status_code == 200
    assert res_delete.json()["status"] == "deleted"

    # Verify List Empty
    res_list_after = client.get(
        "/v1/admin/api-keys",
        headers={"X-Admin-Secret": "test_admin_secret_123"}
    )
    assert len(res_list_after.json()["api_keys"]) == 0
