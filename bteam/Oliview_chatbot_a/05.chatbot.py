"""
Backward Compatibility Shim for 05.chatbot.py
Delegates all calls to bteam.oliview_core.pipeline.
"""

import sys
import os
from typing import Any, Tuple, Iterator, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BTEAM_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(BTEAM_DIR, ".."))

for p in [CURRENT_DIR, BTEAM_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from oliview_core.pipeline import (
    prepare_pipeline_stream,
    generate_pipeline_answer,
    generate_pipeline_answer_stream,
    get_pipeline,
)
from oliview_core.types import (
    StepCode,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
)
from oliview_core.callback import StepCallbackProtocol, StreamlitStepCallback


def create_chatbot() -> Any:
    """Returns singleton pipeline orchestrator instance."""
    return get_pipeline()


def prepare_chatbot_stream(
    chatbot: Any,
    question: str,
    callback: Optional[StepCallbackProtocol] = None,
    category_hint: Optional[str] = None,
) -> Tuple[Iterator[str], RagExecutionMetadata]:
    """2-Stage retrieval preparation delegating to oliview_core."""
    return prepare_pipeline_stream(
        question=question,
        callback=callback,
        category_hint=category_hint,
    )


def generate_chatbot_answer(
    chatbot: Any,
    question: str,
    callback: Optional[StepCallbackProtocol] = None,
) -> str:
    """Synchronous answer generation."""
    return generate_pipeline_answer(question=question, callback=callback)


def generate_chatbot_answer_stream(
    chatbot: Any,
    question: str,
    callback: Optional[StepCallbackProtocol] = None,
) -> Iterator[str]:
    """Generator answer streaming."""
    return generate_pipeline_answer_stream(question=question, callback=callback)