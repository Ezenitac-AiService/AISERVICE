from __future__ import annotations

from collections.abc import Mapping

SERVICE_ENV_ALLOWLIST: dict[str, frozenset[str]] = {
    "pipeline_runner": frozenset(
        {
            "APP_RUN_MODE",
            "DEPLOYMENT_STAGE",
            "MYSQL_WRITE_ENDPOINT",
            "BLUE_MYSQL_ENDPOINT",
            "REDIS_ENDPOINT",
            "BLUE_REDIS_ENDPOINT",
            "CHROMA_WRITE_ENDPOINT",
            "BLUE_CHROMA_ENDPOINT",
            "GATEWAY_ENDPOINTS",
            "MODEL_GATEWAY_ENDPOINTS",
            "CRAWLER_ENDPOINT",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
        }
    ),
    "dashboard_backend": frozenset(
        {
            "APP_RUN_MODE",
            "DEPLOYMENT_STAGE",
            "MYSQL_READ_ENDPOINT",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "REDIS_ENDPOINT",
            "PORT",
        }
    ),
    "chatbot_a": frozenset(
        {
            "APP_RUN_MODE",
            "DEPLOYMENT_STAGE",
            "MYSQL_READ_ENDPOINT",
            "REDIS_ENDPOINT",
            "CHROMA_READ_ENDPOINT",
            "GATEWAY_ENDPOINTS",
            "MODEL_GATEWAY_ENDPOINTS",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "PORT",
        }
    ),
    "chatbot_b": frozenset(
        {
            "APP_RUN_MODE",
            "DEPLOYMENT_STAGE",
            "MYSQL_READ_ENDPOINT",
            "REDIS_ENDPOINT",
            "CHROMA_READ_ENDPOINT",
            "GATEWAY_ENDPOINTS",
            "MODEL_GATEWAY_ENDPOINTS",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "PORT",
        }
    ),
}


def validate_service_env(service: str, values: Mapping[str, str]) -> None:
    allowed = SERVICE_ENV_ALLOWLIST.get(service)
    if allowed is None:
        raise ValueError(f"unknown service: {service}")
    unexpected = sorted(set(values) - allowed)
    if unexpected:
        raise ValueError(
            f"environment keys are not allowed for {service}: {', '.join(unexpected)}"
        )
