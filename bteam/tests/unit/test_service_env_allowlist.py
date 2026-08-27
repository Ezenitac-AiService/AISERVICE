import pytest
from oliview_core.allowlist import validate_service_env


def test_reader_services_reject_write_and_crawler_environment_keys():
    with pytest.raises(ValueError, match="MYSQL_WRITE_ENDPOINT"):
        validate_service_env(
            "dashboard_backend", {"MYSQL_WRITE_ENDPOINT": "mysql-green:3306"}
        )
    with pytest.raises(ValueError, match="CRAWLER_ENDPOINT"):
        validate_service_env(
            "chatbot_a", {"CRAWLER_ENDPOINT": "http://crawler-green"}
        )


def test_pipeline_service_allows_crawler_and_write_environment_keys():
    validate_service_env(
        "pipeline_runner",
        {
            "MYSQL_WRITE_ENDPOINT": "mysql-green:3306",
            "CRAWLER_ENDPOINT": "http://crawler-green",
        },
    )
