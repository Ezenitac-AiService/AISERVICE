"""
Test for Feature 047 (User Story 2):
Verify resilient streaming timeout configuration and client streaming robustness under vLLM queueing.
"""

import pytest
from oliview_core.config import get_settings, AppRunMode
from oliview_core.client import AiGatewayClient


def test_settings_timeout_configuration():
    """Verify that DEMO / development settings have at least 180s timeout budget."""
    settings = get_settings()
    assert settings.timeout_llm_sec >= 180.0
    assert settings.inactivity_timeout_s >= 180.0


def test_client_timeout_profile_initialization():
    """Verify that AiGatewayClient initializes with the resilient inactivity timeout."""
    settings = get_settings()
    client = AiGatewayClient()
    assert client.timeout_llm >= 180.0
    assert client.inactivity_timeout_s >= 180.0
