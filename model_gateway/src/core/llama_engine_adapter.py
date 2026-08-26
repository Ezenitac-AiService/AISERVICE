"""
LlamaCpp Engine Adapter (Spec 018 / T008).
Implements BaseInferenceEngine for llama.cpp server backend.
"""

import os
import json
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
import httpx

from src.core.base_engine import BaseInferenceEngine
from src.core.process_manager import ProcessManager, ProcessState, ProcessStatusEnum
from src.core.config_manager import ConfigManager


class LlamaCppEngineAdapter(BaseInferenceEngine):
    """Adapter wrapping ProcessManager to conform to BaseInferenceEngine."""

    def __init__(self, port: int = 8089, config_manager: Optional[ConfigManager] = None):
        self.port = port
        self.config_manager = config_manager or ConfigManager()
        self.process_manager = ProcessManager(port=self.port, config_manager=self.config_manager)
        self.base_url = f"http://127.0.0.1:{self.port}"

    async def load_model(self, model_id: str, n_ctx: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """Loads target model with verified VRAM into llama-server."""
        effective_n_ctx = n_ctx if n_ctx is not None else self.config_manager.get_current_n_ctx()
        state = await self.process_manager.load_model_vram_verified(model_id, n_ctx=effective_n_ctx)
        return {
            "status": state.status.value if hasattr(state.status, "value") else str(state.status),
            "model_id": state.model_id,
            "port": state.port,
            "error_message": state.error_message
        }

    async def unload_model(self) -> None:
        """Unloads current model."""
        await self.process_manager.stop_process()

    def is_ready(self) -> bool:
        """Checks if process is healthy and ready."""
        return self.process_manager.is_ready()

    async def generate_stream(self, payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Streams tokens from local llama-server /v1/chat/completions."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=300.0) as client:
            async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
                async for line in response.aiter_lines():
                    if line:
                        yield line

    def get_vram_usage(self) -> Dict[str, Any]:
        """Returns VRAM status."""
        return {
            "vram_total_mb": self.process_manager.vram_total,
            "vram_capacity_limit_mb": self.process_manager.vram_max_capacity_mb,
            "status": self.process_manager.state.status.value if hasattr(self.process_manager.state.status, "value") else str(self.process_manager.state.status)
        }
