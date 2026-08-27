from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class RunMode(StrEnum):
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"


class DeploymentStage(StrEnum):
    VALIDATION = "VALIDATION"
    CUTOVER = "CUTOVER"


@dataclass(frozen=True)
class Settings:
    app_run_mode: str = "DEMO"
    deployment_stage: str = "VALIDATION"
    mysql_write_endpoint: str = ""
    blue_mysql_endpoint: str = ""
    chroma_write_endpoint: str = ""
    blue_chroma_endpoint: str = ""
    redis_endpoint: str = ""
    blue_redis_endpoint: str = ""
    model_gateway_endpoints: str = "[]"
    crawler_endpoint: str = ""
    lease_heartbeat_seconds: int = 15
    lease_ttl_seconds: int = 60
    service_name: str = "bteam"
    env: Mapping[str, str] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        mode = str(self.app_run_mode).upper()
        stage = str(self.deployment_stage).upper()
        if mode not in {item.value for item in RunMode}:
            raise ValueError(f"unsupported APP_RUN_MODE: {self.app_run_mode}")
        if stage not in {item.value for item in DeploymentStage}:
            raise ValueError(f"unsupported DEPLOYMENT_STAGE: {self.deployment_stage}")
        if self.lease_ttl_seconds < self.lease_heartbeat_seconds * 3:
            raise ValueError("lease TTL must be at least three heartbeats")

    def validate_data_plane(self) -> None:
        if str(self.deployment_stage).upper() == DeploymentStage.VALIDATION.value:
            pairs = (
                (self.mysql_write_endpoint, self.blue_mysql_endpoint, "MySQL"),
                (self.chroma_write_endpoint, self.blue_chroma_endpoint, "ChromaDB"),
                (self.redis_endpoint, self.blue_redis_endpoint, "Redis"),
            )
            for green, blue, label in pairs:
                if green and blue and green.strip() == blue.strip():
                    raise ValueError(
                        f"VALIDATION {label} endpoint must be isolated from Blue"
                    )

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> Settings:
        source: Mapping[str, str] = values if values is not None else os.environ
        get = lambda key, default="": source.get(key, default)
        canonical_gateway_endpoints = source.get("MODEL_GATEWAY_ENDPOINTS", "").strip()
        legacy_gateway_endpoints = source.get("GATEWAY_ENDPOINTS", "").strip()
        return cls(
            app_run_mode=get("APP_RUN_MODE", "DEMO"),
            deployment_stage=get("DEPLOYMENT_STAGE", "VALIDATION"),
            mysql_write_endpoint=get("MYSQL_WRITE_ENDPOINT"),
            blue_mysql_endpoint=get("BLUE_MYSQL_ENDPOINT"),
            chroma_write_endpoint=get("CHROMA_WRITE_ENDPOINT"),
            blue_chroma_endpoint=get("BLUE_CHROMA_ENDPOINT"),
            redis_endpoint=get("REDIS_ENDPOINT"),
            blue_redis_endpoint=get("BLUE_REDIS_ENDPOINT"),
            model_gateway_endpoints=(
                canonical_gateway_endpoints or legacy_gateway_endpoints or "[]"
            ),
            crawler_endpoint=get("CRAWLER_ENDPOINT"),
            service_name=get("SERVICE_NAME", "bteam"),
            env=source,
        )
