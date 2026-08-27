import pytest

from oliview_core.config import Settings


def test_validation_requires_isolated_write_endpoints():
    settings = Settings(
        app_run_mode="DEMO",
        deployment_stage="VALIDATION",
        mysql_write_endpoint="green-db",
        blue_mysql_endpoint="blue-db",
    )
    settings.validate_data_plane()


def test_validation_rejects_blue_write_endpoint():
    settings = Settings(
        app_run_mode="DEMO",
        deployment_stage="VALIDATION",
        mysql_write_endpoint="blue-db",
        blue_mysql_endpoint="blue-db",
    )
    with pytest.raises(ValueError):
        settings.validate_data_plane()


def test_from_env_reads_process_environment_when_mapping_is_omitted(monkeypatch):
    monkeypatch.setenv("APP_RUN_MODE", "PRODUCTION")
    monkeypatch.setenv("DEPLOYMENT_STAGE", "CUTOVER")

    settings = Settings.from_env()

    assert settings.app_run_mode == "PRODUCTION"
    assert settings.deployment_stage == "CUTOVER"


def test_from_env_supports_canonical_gateway_name_and_legacy_alias():
    canonical = Settings.from_env(
        {"MODEL_GATEWAY_ENDPOINTS": "[{}]", "CRAWLER_ENDPOINT": "http://crawler"}
    )
    legacy = Settings.from_env({"GATEWAY_ENDPOINTS": "[{}]"})

    assert canonical.model_gateway_endpoints == "[{}]"
    assert canonical.crawler_endpoint == "http://crawler"
    assert legacy.model_gateway_endpoints == "[{}]"
