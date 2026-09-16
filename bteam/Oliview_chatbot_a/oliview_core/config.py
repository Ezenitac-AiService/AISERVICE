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
    GATEWAY_SERVER_NAMES: str = Field(default="localhost")
    OLIVIEW_BACKEND_UPSTREAM: str = Field(default="http://oliview_backend:5050")
    OLIVIEW_FRONTEND_UPSTREAM: str = Field(default="http://oliview_frontend:5173")
    CHATBOT_A_UPSTREAM: str = Field(default="http://oliview_chatbot_a:8501")
    CHATBOT_B_UPSTREAM: str = Field(default="http://oliview_chatbot_b:8002")
    PILOS_WEB_UPSTREAM: str = Field(default="http://pilos-web:5000")
    LLM_BASE_URL: str = Field(default="http://model-gateway:8081/v1")
    EMBEDDING_BASE_URL: str = Field(default="http://model-gateway:8090/v1")
    RERANK_BASE_URL: str = Field(default="http://model-gateway:8091/v1")
    MODEL_GATEWAY_HEALTH_URL: str = Field(default="http://model-gateway:8081/health")
    CHATA_HEALTH_URL: str = Field(default="http://oliview_chatbot_a:8501/health")
    CHATB_HEALTH_URL: str = Field(default="http://oliview_chatbot_b:8502/health")
    REDIS_ENDPOINT: str = Field(default="redis://redis:6379/0")
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

    # Hot-swap Feature Flag (Spec 030 / Feature 005)
    feature_langgraph_rag: bool = Field(default=True)

    # Model Names & Parameters
    fast_llm_model: str = Field(default="qwen3.5-4b")
    synthesis_llm_model: str = Field(default="qwen3.5-9b")
    rerank_model: str = Field(default="bge-reranker-v2-m3")
    embedding_model: str = Field(default="bge-m3")

    # Database & Pool Settings
    db_host: str = Field(default="bteam_db")
    db_port: int = Field(default=3306)
    db_user: str = Field(default="bteam_user")
    db_password: str = Field(default="")
    db_name: str = Field(default="oliview_project")
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)
    db_pool_recycle: int = Field(default=1800)

    # Redis In-Memory Settings
    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_socket_timeout: float = Field(default=0.5)
    redis_ttl_session: int = Field(default=259200)
    redis_ttl_embedding: int = Field(default=604800)
    redis_ttl_rerank: int = Field(default=86400)
    redis_ttl_search_pool: int = Field(default=43200)
    redis_ttl_llm_response: int = Field(default=43200)
    redis_ttl_llm_jitter: int = Field(default=3600)
    enable_l5_cache: bool = Field(default=True)

    # Pipeline Timeouts & Sampling Defaults
    timeout_search_sec: float = Field(default=10.0)
    timeout_rerank_sec: float = Field(default=20.0)
    timeout_llm_sec: float = Field(default=180.0)
    inactivity_timeout_s: float = Field(default=180.0)
    max_targets: int = Field(default=3)
    gpu_concurrency_limit: int = Field(default=1)
    candidates_per_target: int = Field(default=15)
    reranked_per_target: int = Field(default=6)
    tokens_per_target: int = Field(default=3500)
    max_single_output_tokens: int = Field(default=1024)
    max_compare_output_tokens: int = Field(default=3072)
    max_input_context_tokens: int = Field(default=10000)
    default_temperature: float = Field(default=0.3)
    default_top_p: float = Field(default=0.85)
    default_repetition_penalty: float = Field(default=1.05)
    # Vector Index Optimization
    chroma_hnsw_search_ef: int = Field(default=64)
    faiss_index_dir: Optional[str] = Field(default=None)
    min_required_n_ctx: int = Field(default=32768)

    @property
    def llm_endpoint(self) -> str:
        return self.LLM_BASE_URL.rstrip("/")

    @property
    def embed_endpoint(self) -> str:
        return self.EMBEDDING_BASE_URL.rstrip("/")

    @property
    def rerank_endpoint(self) -> str:
        return self.RERANK_BASE_URL.rstrip("/")

    def get_context_harness(self, n_ctx: Optional[int] = None) -> ContextHarnessProfile:
        target_ctx = n_ctx or self.min_required_n_ctx
        return compute_context_harness_profile(target_ctx)

    @classmethod
    def from_env(cls) -> "CoreSettings":
        data = {}
        for field_name in cls.model_fields.keys():
            candidates = [field_name, field_name.upper(), field_name.lower()]
            found_val = None
            for cand in candidates:
                if cand in os.environ:
                    found_val = os.environ[cand]
                    break
            if found_val is not None:
                field_type = cls.model_fields[field_name].annotation
                if field_type is int or field_type == int:
                    try:
                        data[field_name] = int(found_val)
                    except ValueError:
                        data[field_name] = found_val
                elif field_type is float or field_type == float:
                    try:
                        data[field_name] = float(found_val)
                    except ValueError:
                        data[field_name] = found_val
                elif field_type is bool or field_type == bool:
                    data[field_name] = found_val.lower() in ("true", "1", "yes")
                else:
                    data[field_name] = found_val
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
        return "http://model-gateway"
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
    discovered_model: str = "qwen3.5-9b"
    discovered_n_ctx: int = 32768
    last_synced_at: float = 0.0
    ttl_seconds: float = 60.0

    def is_valid(self) -> bool:
        return (time.time() - self.last_synced_at) < self.ttl_seconds

    def update(self, model: str, n_ctx: int = 32768):
        self.discovered_model = model
        self.discovered_n_ctx = n_ctx
        self.last_synced_at = time.time()


_discovery_cache = ModelDiscoveryCache()


def compute_context_harness_profile(n_ctx: int = 32768) -> ContextHarnessProfile:
    """
    3-Tier Agentic Context Harness Profile 계산기 (Spec 035).
    게이트웨이 유효 컨텍스트 윈도우 크기에 따라 토큰 예산과 선별 리뷰 수를 동적 산정합니다.
    """
    if n_ctx >= 65536:
        # Tier 3: Ultra (64K~128K+)
        return ContextHarnessProfile(
            total_n_ctx=n_ctx,
            tier_name="ULTRA",
            max_input_tokens=48000,
            max_output_tokens=8192,
            max_compare_output_tokens=8192,
            tokens_per_target=15000,
            reranked_per_target=20,
            candidates_per_target=30,
            max_history_turns=50,
            raw_history_turns=10,
            summary_history_turns=40,
        )
    elif n_ctx >= 32768:
        # Tier 2: 32K Standard (32,768 tokens)
        return ContextHarnessProfile(
            total_n_ctx=n_ctx,
            tier_name="32K_STANDARD",
            max_input_tokens=22000,
            max_output_tokens=4096,
            max_compare_output_tokens=4096,
            tokens_per_target=7000,
            reranked_per_target=12,
            candidates_per_target=20,
            max_history_turns=30,
            raw_history_turns=5,
            summary_history_turns=25,
        )
    else:
        # Tier 1: 16K Baseline (16,384 tokens)
        return ContextHarnessProfile(
            total_n_ctx=max(16384, n_ctx),
            tier_name="16K_BASELINE",
            max_input_tokens=10000,
            max_output_tokens=2048,
            max_compare_output_tokens=3072,
            tokens_per_target=3500,
            reranked_per_target=6,
            candidates_per_target=15,
            max_history_turns=15,
            raw_history_turns=5,
            summary_history_turns=10,
        )



class Settings(BaseModel):
    """Legacy Settings compatibility wrapper."""
    app_run_mode: AppRunMode = Field(default_factory=lambda: AppRunMode(os.getenv("APP_RUN_MODE", "DEMO")))
    server_host: str = Field(default_factory=_detect_default_server_host)
    llm_endpoint: str = Field(default_factory=lambda: os.getenv("LLM_BASE_URL", f"{_detect_default_server_host()}:8001/v1"))
    embedding_endpoint: str = Field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", f"{_detect_default_server_host()}:8002/v1"))
    rerank_endpoint: str = Field(default_factory=lambda: os.getenv("RERANK_BASE_URL", f"{_detect_default_server_host()}:8003/v1"))
    db_host: str = Field(default_factory=_detect_default_db_host)
    db_port: int = Field(default=3306)
    db_user: str = Field(default_factory=lambda: os.getenv("DB_USER", "bteam_user"))
    db_password: str = Field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
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
