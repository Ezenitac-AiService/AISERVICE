import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from src.api.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@patch('src.core.llama_manager.LlamaManager.unload_model')
def test_inference_503(mock_unload, client):
    from src.core.process_manager import ProcessStatusEnum
    from src.core.llama_manager import llama_manager

    def set_unloaded(*args, **kwargs):
        llama_manager.state = ProcessStatusEnum.UNLOADED

    mock_unload.side_effect = set_unloaded

    # Make sure we start in UNLOADED state
    response = client.post("/dashboard/api/unload", headers={"X-Admin-Secret": "aiservice"})
    llama_manager.state = ProcessStatusEnum.UNLOADED
    
    # Try to access /v1/chat/completions
    response = client.post("/v1/chat/completions", json={"prompt": "test"})
    assert response.status_code == 503
    assert "Retry-After" in response.headers
    assert response.headers["Retry-After"] == "10"
