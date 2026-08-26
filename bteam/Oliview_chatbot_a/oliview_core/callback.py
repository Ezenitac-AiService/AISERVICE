"""
Step Callback Protocols and Adapters for Oliview Core.
"""

from typing import Protocol, Any, Optional
from .types import StepEvent, StepCode


class StepCallbackProtocol(Protocol):
    """Abstract protocol for receiving RAG pipeline step notifications."""
    def on_step(self, event: StepEvent) -> None:
        ...


class StreamlitStepCallback:
    """Streamlit status container callback adapter."""
    def __init__(self, status_box: Any):
        self.status = status_box

    def on_step(self, event: StepEvent) -> None:
        try:
            if hasattr(self.status, "write"):
                self.status.write(f"- {event.label}")
        except Exception:
            pass


class LoggingStepCallback:
    """Console / Logger fallback callback adapter."""
    def on_step(self, event: StepEvent) -> None:
        print(f"[{event.step.value}] {event.label} ({event.elapsed_sec:.2f}s)")
