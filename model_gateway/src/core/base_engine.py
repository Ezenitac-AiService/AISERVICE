"""
Base Inference Engine Abstract Interface (Spec 018 / T003).
Provides a unified abstract class for modern LLM inference engines (llama.cpp, vLLM, mock).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator, List


class BaseInferenceEngine(ABC):
    """Abstract Base Class defining the standard lifecycle and inference contract."""

    @abstractmethod
    async def load_model(self, model_id: str, n_ctx: int, **kwargs) -> Dict[str, Any]:
        """Loads target model into GPU VRAM with specified context window.
        
        Args:
            model_id: Identifier of model in catalog (e.g., 'qwen3.5-4b')
            n_ctx: Context window size in tokens
            **kwargs: Engine-specific parameters (e.g., flash_attn, ctk, ctv)
            
        Returns:
            Dictionary containing state and VRAM info
        """
        pass

    @abstractmethod
    async def unload_model(self) -> None:
        """Unloads currently active model and safely releases GPU VRAM."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Returns True if engine process is running and healthy."""
        pass

    @abstractmethod
    async def generate_stream(self, payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Asynchronously streams completion tokens or SSE events.
        
        Args:
            payload: OpenAI-compatible completion request payload
            
        Yields:
            Token strings or SSE chunk payloads
        """
        pass

    @abstractmethod
    def get_vram_usage(self) -> Dict[str, Any]:
        """Returns current GPU VRAM utilization statistics."""
        pass
