"""
Oliview Core (bteam.oliview_core)
Unified RAG Engine, Gateway Client, and Domain Utilities for Oliview AI Chatbot.
"""

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
from .guardrail import PromptInjectionGuardrail, guardrail
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
    "prepare_pipeline_stream",
    "generate_pipeline_answer",
    "generate_pipeline_answer_stream",
]

