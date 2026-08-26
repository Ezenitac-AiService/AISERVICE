"""
Unit tests for ApiKeyManager and Admin Secret verification.
"""

import os
import tempfile
import pytest
from src.core.api_key_manager import ApiKeyManager, ApiKeyEntity


def test_api_key_manager_crud_and_verification(tmp_path):
    config_path = str(tmp_path / "server_config.json")
    manager = ApiKeyManager(config_path=config_path)

    # 1. Key Generation
    entity, raw_key = manager.generate_key(name="TestClientKey")
    assert raw_key.startswith("sk-vllm-")
    assert entity.name == "TestClientKey"
    assert entity.masked_key.startswith("sk-***")

    # 2. Key Verification
    from src.core.config_manager import ConfigManager
    cm = ConfigManager(config_path=config_path)
    cm._write_atomic_server_config(cm.get_server_config(), api_key_enabled=True)


    is_valid, masked = manager.verify_key(raw_key)
    assert is_valid is True
    assert masked == entity.masked_key

    # Invalid Key Verification
    is_valid_wrong, masked_wrong = manager.verify_key("sk-vllm-invalidkey12345678")
    assert is_valid_wrong is False
    assert masked_wrong is None

    # 3. List Keys
    keys = manager.list_keys()
    assert len(keys) == 1
    assert keys[0].key_id == entity.key_id

    # 4. Revoke Key
    revoked = manager.revoke_key(entity.key_id)
    assert revoked is True
    assert len(manager.list_keys()) == 0


def test_admin_secret_verification(tmp_path):
    config_path = str(tmp_path / "server_config.json")
    manager = ApiKeyManager(config_path=config_path)

    from src.core.config_manager import ConfigManager
    cm = ConfigManager(config_path=config_path)
    cm.set("admin_secret", "custom_secret_999")

    assert manager.verify_admin_secret("custom_secret_999") is True
    assert manager.verify_admin_secret("wrong_password") is False
