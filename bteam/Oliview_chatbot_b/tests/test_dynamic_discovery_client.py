import pytest
import time
from unittest.mock import patch, MagicMock
from oliview_core.client import AiGatewayClient
from oliview_core.config import CoreSettings, ModelDiscoveryCache

def test_model_discovery_cache_ttl():
    """Verify ModelDiscoveryCache respects 60s TTL."""
    cache = ModelDiscoveryCache(discovered_model="qwen3.5-2b", discovered_n_ctx=16384, last_synced_at=time.time(), ttl_seconds=60.0)
    assert cache.is_valid() is True
    assert cache.discovered_model == "qwen3.5-2b"
    assert cache.discovered_n_ctx == 16384

    # Expire cache
    cache.last_synced_at = time.time() - 61.0
    assert cache.is_valid() is False

def test_client_discover_active_model_success():
    """Verify AiGatewayClient fetches active model and caches it."""
    client = AiGatewayClient()
    mock_resp = {
        "active_model": "qwen3.5-2b",
        "current_n_ctx": 16384,
        "vram_total_mb": 8192
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.read.return_value = b'{"active_model": "qwen3.5-2b", "current_n_ctx": 16384}'
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        discovered = client.discover_active_model(force_refresh=True)
        assert discovered == "qwen3.5-2b"
        assert client._discovery_cache.is_valid() is True

def test_client_discover_active_model_fallback():
    """Verify AiGatewayClient gracefully falls back to config setting on network error."""
    client = AiGatewayClient()
    client._discovery_cache.last_synced_at = 0.0 # invalid
    with patch("urllib.request.urlopen", side_effect=Exception("Network down")):
        discovered = client.discover_active_model(force_refresh=True)
        assert discovered == client.settings.synthesis_llm_model
