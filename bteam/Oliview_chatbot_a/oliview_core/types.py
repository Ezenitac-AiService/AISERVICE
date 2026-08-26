"""
Data Models & Type Definitions for Oliview Core.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StepCode(str, Enum):
    QUEUE_WAITING = "QUEUE_WAITING"       # Spec 031: GPU 큐 대기 중
    INTENT_ANALYSIS = "INTENT_ANALYSIS"
    HYBRID_SEARCH = "HYBRID_SEARCH"
    RERANKING = "RERANKING"
    LLM_SYNTHESIS = "LLM_SYNTHESIS"
    ERROR = "ERROR"


@dataclass
class StepEvent:
    step: StepCode
    label: str
    elapsed_sec: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


class ReferenceReview(BaseModel):
    review_id: int
    product_name: str
    product_url: str = ""
    clean_text: str
    original_text: str = ""
    sentiment: str = "NEUTRAL"
    relevance_score: float = 0.0
    brand: str = ""
    category: str = ""


class RagExecutionMetadata(BaseModel):
    total_latency_sec: float = 0.0
    search_latency_sec: float = 0.0
    rerank_latency_sec: float = 0.0
    selected_review_count: int = 0
    model_name: str = "qwen3.5-4b"
    fallback_used: bool = False
    reference_reviews: List[ReferenceReview] = Field(default_factory=list)


class IntentAnalysisResult(BaseModel):
    product_name: Optional[str] = None
    attribute: Optional[str] = None
    intent_type: str = "general"
    requires_dual_search: bool = False
    search_queries: List[str] = Field(default_factory=list)


# ────────────────────────────────────────────────────────────────────────────
# Spec 021: Security Entities & Guardrail Data Models
# ────────────────────────────────────────────────────────────────────────────

class InjectionDetectionResult(BaseModel):
    is_blocked: bool = False
    risk_level: str = "NONE"  # "NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"
    matched_rule: Optional[str] = None
    sanitized_text: str = ""
    execution_time_ms: float = 0.0
    reason: Optional[str] = None


class SecurityEventLog(BaseModel):
    timestamp: float
    event_id: str
    client_ip: Optional[str] = None
    session_id: Optional[str] = None
    user_query: str
    matched_rule: str
    risk_level: str
    action_taken: str = "BLOCKED_SAFE_RESPONSE"


class SandboxedPromptPayload(BaseModel):
    system_prompt: str
    user_content: str
    canary_token: str


class GateVerdict(str, Enum):
    ALLOW = "ALLOW"
    BLOCKED_INJECTION = "BLOCKED_INJECTION"
    BLOCKED_OUT_OF_DOMAIN = "BLOCKED_OUT_OF_DOMAIN"
    BLOCKED_MEDICAL_TOXICITY = "BLOCKED_MEDICAL_TOXICITY"
    BLOCKED_DEFAMATION = "BLOCKED_DEFAMATION"


class EarlyGateDecision(BaseModel):
    verdict: GateVerdict
    is_blocked: bool
    refusal_message: str
    matched_rule: str
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    latency_ms: float
    guard_source: str  # "TIER_1A_RULE", "TIER_1B_MODEL", "SECURITY_CACHE"
    sanitized_query: str


class SecurityMetricsEvent(BaseModel):
    timestamp: float
    event_id: str
    client_ip: Optional[str] = None
    session_id: Optional[str] = None
    masked_query: str
    verdict: GateVerdict
    matched_rule: str
    risk_level: str
    latency_ms: float
    action_taken: str


# ────────────────────────────────────────────────────────────────────────────
# Spec 032: L5 LLM Response Cache Entities & Data Models
# ────────────────────────────────────────────────────────────────────────────

class L5CacheKeyParams(BaseModel):
    tenant_id: str = Field(default="chata", description="서비스 테넌트 식별자 (chata, chatb)")
    rewritten_query: str = Field(..., description="대명사 해소 및 탈맥락화된 사용자 질의")
    doc_ids: List[str] = Field(default_factory=list, description="리랭킹 상위 선별 문서 ID 목록")
    model_id: str = Field(default="qwen3.5-2b", description="LLM 모델 식별자")
    prompt_version: str = Field(default="v1.0", description="시스템 프롬프트 템플릿 버전")


class L5ResponseCachePayload(BaseModel):
    response_text: str = Field(..., description="완성된 전체 마크다운 답변 텍스트 (길이 >= 20)")
    model_id: str = Field(default="qwen3.5-2b", description="생성에 사용된 모델 식별자")
    prompt_version: str = Field(default="v1.0", description="프롬프트 템플릿 버전")
    tenant_id: str = Field(default="chata", description="서비스 테넌트 식별자")
    doc_ids_hash: str = Field(default="", description="참조된 RAG 문서 목록 해시")
    created_at: float = Field(..., description="캐시 생성 유닉스 타임스탬프")
    estimated_tokens: int = Field(default=0, description="생성된 토큰 수 추정치")


class CacheReplayChunk(BaseModel):
    chunk_index: int = Field(..., description="스트리밍 청크 순번 (0-indexed)")
    delta_content: str = Field(..., description="단어/공백 단위 텍스트 증분")
    is_cached: bool = Field(default=True, description="캐시 히트 여부 플래그")
    latency_saved_s: float = Field(default=0.0, description="절감된 GPU 추론 시간 추정치")
