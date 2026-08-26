"""
Centralized Configuration Manager for Oliview Core (Spec 035 - 3-Tier Context Harness).
"""

import os
import socket
from functools import lru_cache
from typing import Optional
from pydantic import BaseModel, Field
from dataclasses import dataclass
import time

from .graph_state import ContextHarnessProfile


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
    """In-memory cache for dynamic active model and context discovery (Spec 033 / Spec 035)."""
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


def compute_context_harness_profile(n_ctx: int = 16384) -> ContextHarnessProfile:
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


class CoreSettings(BaseModel):
    # Model Gateway Configuration
    server_host: str = Field(default_factory=_detect_default_server_host)
    main_port: int = Field(default_factory=lambda: int(os.getenv("MAIN_PORT", "8081")))
    embed_port: int = Field(default_factory=lambda: int(os.getenv("EMBED_PORT", "8090")))
    rerank_port: int = Field(default_factory=lambda: int(os.getenv("RERANK_PORT", "8091")))

    # Model Names (Spec 033: Dynamic Discovery & Hardware Alignment)
    fast_llm_model: str = Field(default_factory=lambda: os.getenv("FAST_LLM_MODEL", "qwen3.5-2b"))
    synthesis_llm_model: str = Field(default_factory=lambda: os.getenv("SYNTHESIS_LLM_MODEL", "qwen3.5-2b"))
    auto_discover_model: bool = Field(default_factory=lambda: os.getenv("AUTO_DISCOVER_MODEL", "true").lower() in ("true", "1", "yes"))
    discovery_ttl_seconds: float = Field(default=60.0, description="동적 모델 탐색 캐시 TTL (초)")
    min_required_n_ctx: int = Field(default=16384, description="최소 보장 대용량 컨텍스트 윈도우")
    rerank_model: str = Field(default_factory=lambda: os.getenv("RERANK_MODEL", "bge-reranker-v2-m3"))
    embedding_model: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "bge-m3"))

    # Database & Connection Pool Configuration
    db_host: str = Field(default_factory=_detect_default_db_host)
    db_port: int = Field(default_factory=lambda: int(os.getenv("DB_PORT", "3306")))
    db_user: str = Field(default_factory=lambda: os.getenv("DB_USER", "gp123"))
    db_password: str = Field(default_factory=lambda: os.getenv("DB_PASSWORD", "GP123!"))
    db_name: str = Field(default_factory=lambda: os.getenv("DB_NAME", "oliview_project"))
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    # Redis In-Memory Infrastructure Configuration (Spec 019 / 030 / 035)
    redis_host: str = Field(default_factory=lambda: os.getenv("REDIS_HOST", "127.0.0.1" if not _is_running_in_docker() else "redis"))
    redis_port: int = Field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    redis_socket_timeout: float = 0.2     # Spec 030 FR-024: Fail-Fast 소켓 타임아웃
    redis_ttl_session: int = 259200       # L4: 3 days (LangGraph checkpoint & turn history)
    redis_ttl_embedding: int = 604800     # L2: 7 days (BGE-M3 embedding)
    redis_ttl_rerank: int = 86400         # L3: 24 hours (Reranker scores)
    redis_ttl_search_pool: int = 43200    # L1: 12 hours (1차 검색 풀 캐시)
    redis_ttl_llm_response: int = 43200   # L5: 12 hours (Spec 032: LLM 완성 응답 캐시)
    redis_ttl_llm_jitter: int = 3600      # L5: ±1 hour 무작위 Jitter 분산
    enable_l5_cache: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_L5_CACHE", "true").lower() in ("true", "1", "yes")
    )

    # ChromaDB Vector Index Optimization (Spec 019)
    chroma_hnsw_search_ef: int = 64
    faiss_index_dir: Optional[str] = Field(default_factory=lambda: os.getenv("FAISS_INDEX_DIR", None))

    # Operation Mode & Lenient Timeout Profiles (Spec 035 / Spec 037: development vs production)
    rag_operation_mode: str = Field(
        default_factory=lambda: os.getenv("ENVIRONMENT_MODE", os.getenv("RAG_OPERATION_MODE", "development")).lower()
    )

    # Lenient Timeouts (seconds) - Spec 037 POC Demo Friendly
    timeout_search_sec: float = Field(default_factory=lambda: 10.0 if os.getenv("ENVIRONMENT_MODE", os.getenv("RAG_OPERATION_MODE", "development")).lower() in ("development", "dev", "poc") else 5.0)
    timeout_rerank_sec: float = Field(default_factory=lambda: 20.0 if os.getenv("ENVIRONMENT_MODE", os.getenv("RAG_OPERATION_MODE", "development")).lower() in ("development", "dev", "poc") else 5.0)
    timeout_llm_sec: float = Field(default_factory=lambda: 180.0 if os.getenv("ENVIRONMENT_MODE", os.getenv("RAG_OPERATION_MODE", "development")).lower() in ("development", "dev", "poc") else 60.0)
    inactivity_timeout_s: float = Field(default_factory=lambda: 45.0 if os.getenv("ENVIRONMENT_MODE", os.getenv("RAG_OPERATION_MODE", "development")).lower() in ("development", "dev", "poc") else 15.0)

    # 2-Stage Sampling Defaults (Spec 037: Top-P Nucleus Sampling)
    default_top_p: float = Field(default=0.85, description="Qwen 3.5 Token-level Nucleus Sampling Top-P")
    default_temperature: float = Field(default=0.3, description="Qwen 3.5 Token Generation Temperature")
    default_repetition_penalty: float = Field(default=1.05, description="Repetition Penalty")

    # 3-Tier Dynamic Context Harness Defaults
    max_targets: int = 3
    gpu_concurrency_limit: int = 3
    candidates_per_target: int = 15
    reranked_per_target: int = 6
    tokens_per_target: int = 3500
    max_single_output_tokens: int = 1024
    max_compare_output_tokens: int = 3072
    max_input_context_tokens: int = 10000

    # Security & Early Intent Guardrail Configuration
    enable_early_guardrail: bool = Field(default_factory=lambda: os.getenv("ENABLE_EARLY_GUARDRAIL", "true").lower() in ("true", "1", "yes"))
    enable_prompt_guard_86m: bool = Field(default_factory=lambda: os.getenv("ENABLE_PROMPT_GUARD_86M", "true").lower() in ("true", "1", "yes"))
    prompt_guard_model_name: str = Field(default_factory=lambda: os.getenv("PROMPT_GUARD_MODEL_NAME", "meta-llama/Llama-Prompt-Guard-2-86M"))

    # Hot-Swap Feature Flag (Spec 030 FR-030)
    feature_langgraph_rag: bool = Field(
        default_factory=lambda: os.getenv("FEATURE_LANGGRAPH_RAG", "true").lower() in ("true", "1", "yes")
    )

    def get_context_harness(self, n_ctx: Optional[int] = None) -> ContextHarnessProfile:
        target_ctx = n_ctx or self.min_required_n_ctx
        return compute_context_harness_profile(target_ctx)

    @property
    def llm_endpoint(self) -> str:
        return f"{self.server_host.rstrip('/')}:{self.main_port}/v1"

    @property
    def embed_endpoint(self) -> str:
        return f"{self.server_host.rstrip('/')}:{self.embed_port}/v1"

    @property
    def rerank_endpoint(self) -> str:
        return f"{self.server_host.rstrip('/')}:{self.rerank_port}/v1"


@lru_cache(maxsize=1)
def get_settings() -> CoreSettings:
    """Returns singleton settings instance."""
    return CoreSettings()
