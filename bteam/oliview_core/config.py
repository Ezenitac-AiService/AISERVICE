"""
Centralized Configuration Manager for Oliview Core (Spec 048 / Constitution Principle VII).
"""

import os
import socket
from enum import Enum
from functools import lru_cache
from typing import Optional
from pydantic import BaseModel, Field
from dataclasses import dataclass
import time

from .graph_state import ContextHarnessProfile


class AppRunMode(str, Enum):
    """Constitution Principle VI: Dynamic execution environment mode."""
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"


class CoreSettings(BaseModel):
    """SSOT Pydantic Settings matching contracts/runtime_environment_schema.json."""
    APP_RUN_MODE: AppRunMode = Field(default=AppRunMode.DEMO)
    GATEWAY_PORT: int = Field(default=80, ge=1, le=65535)
    GATEWAY_ALT_PORT: int = Field(default=8080, ge=1, le=65535)
    CHATBOT_A_PORT: int = Field(default=8501, ge=1, le=65535)
    CHATBOT_B_PORT: int = Field(default=8502, ge=1, le=65535)
    GATEWAY_SERVER_NAMES: str = Field(default="localhost ezenitac.duckdns.org 1.250.5.161")
    OLIVIEW_BACKEND_UPSTREAM: str = Field(default="http://oliview_backend:5050")
    OLIVIEW_FRONTEND_UPSTREAM: str = Field(default="http://oliview_frontend:5173")
    CHATBOT_A_UPSTREAM: str = Field(default="http://oliview_chatbot_a:8501")
    CHATBOT_B_UPSTREAM: str = Field(default="http://oliview_chatbot_b:8002")
    PILOS_WEB_UPSTREAM: str = Field(default="http://pilos-web:5000")
    LLM_BASE_URL: str = Field(default="http://127.0.0.1:8081/v1")
    EMBEDDING_BASE_URL: str = Field(default="http://127.0.0.1:8090/v1")
    RERANK_BASE_URL: str = Field(default="http://127.0.0.1:8091/v1")
    MODEL_GATEWAY_HEALTH_URL: str = Field(default="http://127.0.0.1:8081/health")
    CHATA_HEALTH_URL: str = Field(default="http://127.0.0.1:8501/health")
    CHATB_HEALTH_URL: str = Field(default="http://127.0.0.1:8502/health")
    REDIS_ENDPOINT: str = Field(default="redis://127.0.0.1:6379/0")
    ENABLE_EXTERNAL_VLLM: bool = Field(default=False)
    CHAT_BEARER_SECRET_REF: str = Field(default="vault://keys/chat_bearer")
    CHAT_SESSION_COOKIE_NAME: str = Field(default="aiservice_session")
    CHAT_SESSION_TTL_SECONDS: int = Field(default=86400, ge=60)
    CHAT_CSRF_HEADER_NAME: str = Field(default="X-CSRF-Token")
    CHAT_RATE_LIMIT_REQUESTS: int = Field(default=60, ge=1)
    CHAT_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1)
    CHAT_SERVICE_CONCURRENCY: int = Field(default=10, ge=1)
    CHAT_QUERY_MAX_CHARS: int = Field(default=4000, ge=1)
    CHAT_OUTPUT_TOKEN_CAP: int = Field(default=2048, ge=1)
    CHAT_TIMEOUT_MS: int = Field(default=20000, ge=1000)

    @classmethod
    def from_env(cls) -> "CoreSettings":
        data = {}
        for field_name in cls.model_fields.keys():
            if field_name in os.environ:
                val = os.environ[field_name]
                field_type = cls.model_fields[field_name].annotation
                if field_type is int or field_type == int:
                    try:
                        data[field_name] = int(val)
                    except ValueError:
                        data[field_name] = val
                elif field_type is bool or field_type == bool:
                    data[field_name] = val.lower() in ("true", "1", "yes")
                else:
                    data[field_name] = val
        return cls(**data)


@lru_cache(maxsize=1)
def get_settings() -> CoreSettings:
    return CoreSettings.from_env()


def _is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "1"


def _detect_default_server_host() -> str:
    env_val = os.getenv("SERVER_HOST")
    if env_val:
        return env_val
    if _is_running_in_docker():
        return "http://vllm-serv-gateway"
    return "http://127.0.0.1"


def _detect_default_db_host() -> str:
    env_val = os.getenv("DB_HOST")
    if env_val:
        return env_val
    if _is_running_in_docker():
        return "bteam_db"
    return "127.0.0.1"


@dataclass
class ModelDiscoveryCache:
    """In-memory cache for dynamic active model and context discovery."""
    discovered_model: str = "qwen3.5-2b"
    discovered_n_ctx: int = 16384
    last_synced_at: float = 0.0
    ttl_seconds: float = 60.0

    def is_valid(self) -> bool:
        return (time.time() - self.last_synced_at) < self.ttl_seconds

    def update(self, model: str, n_ctx: int = 16384):
        self.discovered_model = model
        self.discovered_n_ctx = n_ctx
        self.last_synced_at = time.time()


_discovery_cache = ModelDiscoveryCache()


class Settings(BaseModel):
    """Legacy Settings compatibility wrapper."""
    app_run_mode: AppRunMode = Field(default_factory=lambda: AppRunMode(os.getenv("APP_RUN_MODE", "DEMO")))
    server_host: str = Field(default_factory=_detect_default_server_host)
    llm_endpoint: str = Field(default_factory=lambda: os.getenv("LLM_BASE_URL", f"{_detect_default_server_host()}:8001/v1"))
    embedding_endpoint: str = Field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", f"{_detect_default_server_host()}:8002/v1"))
    rerank_endpoint: str = Field(default_factory=lambda: os.getenv("RERANK_BASE_URL", f"{_detect_default_server_host()}:8003/v1"))
    db_host: str = Field(default_factory=_detect_default_db_host)
    db_port: int = Field(default=3306)
    db_user: str = Field(default_factory=lambda: os.getenv("DB_USER", "oliview"))
    db_password: str = Field(default_factory=lambda: os.getenv("DB_PASSWORD", "oliview1234"))
    db_name: str = Field(default_factory=lambda: os.getenv("DB_NAME", "oliview_db"))
    redis_endpoint: str = Field(default_factory=lambda: os.getenv("REDIS_ENDPOINT", "redis://127.0.0.1:6379/0"))

    # Spec 048 Retrieval Parameters (Initial Candidates)
    document_score_threshold: float = Field(default=0.85)
    second_score_threshold: float = Field(default=0.60)
    cliff_delta: float = Field(default=0.25)
    max_selected_reviews: int = Field(default=20)


@lru_cache(maxsize=1)
def get_legacy_settings() -> Settings:
    return Settings()
