import json
import os
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, ValidationError

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "specs" / "048-anti-fictional-user-and-citation-fidelity" / "contracts"


def get_runtime_schema() -> dict:
    path = CONTRACTS_DIR / "runtime_environment_schema.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_valid_sample_env() -> dict:
    return {
        "APP_RUN_MODE": "DEMO",
        "GATEWAY_PORT": 80,
        "GATEWAY_ALT_PORT": 8080,
        "CHATBOT_A_PORT": 8501,
        "CHATBOT_B_PORT": 8502,
        "GATEWAY_SERVER_NAMES": "localhost aiservice.local",
        "OLIVIEW_BACKEND_UPSTREAM": "http://127.0.0.1:8000",
        "OLIVIEW_FRONTEND_UPSTREAM": "http://127.0.0.1:3000",
        "CHATBOT_A_UPSTREAM": "http://127.0.0.1:8501",
        "CHATBOT_B_UPSTREAM": "http://127.0.0.1:8502",
        "PILOS_WEB_UPSTREAM": "http://127.0.0.1:8503",
        "LLM_BASE_URL": "http://127.0.0.1:8001/v1",
        "EMBEDDING_BASE_URL": "http://127.0.0.1:8002/v1",
        "RERANK_BASE_URL": "http://127.0.0.1:8003/v1",
        "MODEL_GATEWAY_HEALTH_URL": "http://127.0.0.1:8001/health",
        "CHATA_HEALTH_URL": "http://127.0.0.1:8501/health",
        "CHATB_HEALTH_URL": "http://127.0.0.1:8502/health",
        "REDIS_ENDPOINT": "redis://127.0.0.1:6379/0",
        "ENABLE_EXTERNAL_VLLM": False,
        "CHAT_BEARER_SECRET_REF": "vault://keys/chat_bearer",
        "CHAT_SESSION_COOKIE_NAME": "aiservice_session",
        "CHAT_SESSION_TTL_SECONDS": 86400,
        "CHAT_CSRF_HEADER_NAME": "X-CSRF-Token",
        "CHAT_RATE_LIMIT_REQUESTS": 60,
        "CHAT_RATE_LIMIT_WINDOW_SECONDS": 60,
        "CHAT_SERVICE_CONCURRENCY": 10,
        "CHAT_QUERY_MAX_CHARS": 4000,
        "CHAT_OUTPUT_TOKEN_CAP": 2048,
        "CHAT_TIMEOUT_MS": 20000,
    }


def test_runtime_environment_schema_valid_env():
    schema = get_runtime_schema()
    validator = Draft202012Validator(schema)
    env = get_valid_sample_env()
    validator.validate(env)


def test_runtime_environment_schema_missing_required_fails():
    schema = get_runtime_schema()
    validator = Draft202012Validator(schema)
    env = get_valid_sample_env()
    del env["REDIS_ENDPOINT"]
    with pytest.raises(ValidationError):
        validator.validate(env)


def test_runtime_environment_schema_invalid_port():
    schema = get_runtime_schema()
    validator = Draft202012Validator(schema)
    env = get_valid_sample_env()
    env["CHATBOT_A_PORT"] = 99999  # > 65535
    with pytest.raises(ValidationError):
        validator.validate(env)


def test_config_py_and_renderer_red_gate():
    """RED GATE: Asserts that oliview_core.config Settings loads runtime environment
    and scripts.render_gateway_config exists. Fails until Phase 3 implementation."""
    try:
        from oliview_core.config import CoreSettings  # type: ignore
        settings = CoreSettings()
        assert settings is not None
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: CoreSettings not implemented in oliview_core.config: {exc}")

    render_script = Path(__file__).resolve().parents[3] / "scripts" / "render_gateway_config.py"
    assert render_script.exists(), "RED GATE: scripts/render_gateway_config.py does not exist yet"
