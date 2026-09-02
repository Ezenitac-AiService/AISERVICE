"""
Oliview Core (bteam.oliview_core)
Unified RAG Engine, Gateway Client, and Domain Utilities for Oliview AI Chatbot.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

__version__ = "1.0.0"

from .types import (
    StepCode,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
    IntentAnalysisResult,
    InjectionDetectionResult,
    SecurityEventLog,
    SandboxedPromptPayload,
)
from .config import CoreSettings, get_settings
from .client import AiGatewayClient
from .callback import StepCallbackProtocol, StreamlitStepCallback
from .guardrail import (
    PromptInjectionGuardrail,
    guardrail,
    GroundednessSanitizer,
    CitationView,
    SanitizationResult,
    verify_exact_quote_match,
    sanitize_citation_quote,
)
from .security import (
    inspect_input_security,
    redact_sensitive_pii,
    compute_effective_limits,
    SecurityInspectionResult,
)
from .rate_limit import RedisRateLimiter
from .prompts import (
    PromptPersonaAdapter,
    PersonaType,
    ServiceIdentity,
)
from .nodes.synthesis_node import (
    StreamingTokenInterceptor,
    execute_synthesis_node,
)


@dataclass
class ProductLinkCard:
    """Structured validated product link card entity."""
    product_id: str
    product_name: str
    product_url: str
    brand_name: Optional[str] = None
    image_url: Optional[str] = None
    price_krw: Optional[int] = None
    discount_rate: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    is_safe_url: bool = True

    def __post_init__(self):
        # Validate allowlisted host
        try:
            parsed = urlparse(self.product_url)
            allowlist = {"oliveyoung.co.kr", "www.oliveyoung.co.kr", "m.oliveyoung.co.kr", "localhost", "127.0.0.1"}
            if parsed.hostname not in allowlist:
                self.is_safe_url = False
        except Exception:
            self.is_safe_url = False


@dataclass
class PipelineStageEvent:
    """4-stage pipeline event tuple."""
    stage: str  # 'retrieve' | 'rerank' | 'synthesis' | 'guardrail'
    status: str  # 'started' | 'in_progress' | 'completed' | 'failed'
    latency_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class ContextReviewRegistry:
    """In-memory registry maintaining context review mappings and bounds."""

    def __init__(self, reviews: Optional[List[Dict[str, Any]]] = None):
        self.reviews = reviews or []

    @property
    def count(self) -> int:
        return len(self.reviews)

    def get_review(self, index: int) -> Optional[Dict[str, Any]]:
        if 1 <= index <= len(self.reviews):
            return self.reviews[index - 1]
        return None


try:
    from .pipeline import (
        prepare_pipeline_stream,
        generate_pipeline_answer,
        generate_pipeline_answer_stream,
    )
except ImportError:
    prepare_pipeline_stream = None
    generate_pipeline_answer = None
    generate_pipeline_answer_stream = None

__all__ = [
    "__version__",
    "StepCode",
    "StepEvent",
    "ReferenceReview",
    "RagExecutionMetadata",
    "IntentAnalysisResult",
    "InjectionDetectionResult",
    "SecurityEventLog",
    "SandboxedPromptPayload",
    "CoreSettings",
    "get_settings",
    "AiGatewayClient",
    "StepCallbackProtocol",
    "StreamlitStepCallback",
    "PromptInjectionGuardrail",
    "guardrail",
    "GroundednessSanitizer",
    "CitationView",
    "SanitizationResult",
    "verify_exact_quote_match",
    "sanitize_citation_quote",
    "inspect_input_security",
    "redact_sensitive_pii",
    "compute_effective_limits",
    "SecurityInspectionResult",
    "RedisRateLimiter",
    "PromptPersonaAdapter",
    "PersonaType",
    "ServiceIdentity",
    "StreamingTokenInterceptor",
    "execute_synthesis_node",
    "ProductLinkCard",
    "PipelineStageEvent",
    "ContextReviewRegistry",
    "prepare_pipeline_stream",
    "generate_pipeline_answer",
    "generate_pipeline_answer_stream",
]
