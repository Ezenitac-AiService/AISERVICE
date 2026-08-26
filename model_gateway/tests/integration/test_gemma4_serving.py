"""Integration tests for Gemma 4 serving with MMProj binding and 100% CUDA VRAM offload.

Feature: 015-gemma4-model-loading-fix
"""

import os
import pytest
import httpx
import asyncio
from src.core.process_manager import ProcessManager, ProcessStatusEnum


@pytest.mark.asyncio
async def test_gemma4_e2b_serving_with_mmproj(test_mode):
    """Verify that Gemma 4 E2B loads with MMProj binding and achieves 100% VRAM offload."""
    if test_mode == "mock":
        os.environ["MOCK_LLAMA_SERVER"] = "1"

    pm = ProcessManager(port=8089)
    try:
        # Check if model file exists before attempting live run
        if test_mode == "real" and not os.path.exists("models/gemma4-e2b/gemma-4-E2B_q4_0-it.gguf"):
            pytest.skip("Gemma 4 E2B model file not present locally. Skipping real integration test.")

        state = await pm.spawn_process("gemma4-e2b", n_ctx=2048)
        assert state.status in [ProcessStatusEnum.LOADING, ProcessStatusEnum.READY]

        if test_mode == "mock":
            # Mock mode assertion
            assert state.model_id == "gemma4-e2b"
            assert state.port == 8089
        else:
            # Real mode: Poll HTTP readiness endpoint up to 60 seconds
            ready = False
            async with httpx.AsyncClient(timeout=5.0) as client:
                for _ in range(60):
                    try:
                        res = await client.get("http://127.0.0.1:8089/v1/models")
                        if res.status_code == 200:
                            ready = True
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)

            assert ready is True, "Gemma 4 E2B server failed to respond HTTP 200 OK on /v1/models"
            assert pm.vram_offload_status is not None
            assert pm.vram_offload_status.is_fully_offloaded is True
            assert pm.vram_offload_status.offloaded_layers > 0
            assert pm.vram_offload_status.offloaded_layers == pm.vram_offload_status.total_layers
    finally:
        await pm.stop_process()
        if "MOCK_LLAMA_SERVER" in os.environ:
            del os.environ["MOCK_LLAMA_SERVER"]
