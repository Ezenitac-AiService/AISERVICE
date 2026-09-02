"""
Auxiliary Model Manager for Embedding and Reranker instances (FR-001, FR-006, FR-007).
Manages multi-instance llama-server subprocesses on dedicated ports (8090 for bge-m3, 8091 for bge-reranker-v2-m3),
including background healthchecking and automatic crash recovery.
"""

import asyncio
import os
import time
from typing import Optional, Dict, Any
import httpx

from src.core.config_manager import ConfigManager
from src.core.process_manager import ProcessManager, ProcessStatusEnum, ProcessState
from src.core.model_downloader import ModelDownloader


class AuxiliaryModelManager:
    """Manages dedicated background llama-server instances for embedding and reranking tasks."""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        server_cfg = self.config_manager.get_server_config()

        self.embedding_port = server_cfg.get("embedding_backend_port", 8090)
        self.rerank_port = server_cfg.get("rerank_backend_port", 8091)
        self.embedding_enabled = server_cfg.get("embedding_enabled", True)
        self.rerank_enabled = server_cfg.get("rerank_enabled", True)

        self.embedding_pm = ProcessManager(port=self.embedding_port, config_manager=self.config_manager)
        self.rerank_pm = ProcessManager(port=self.rerank_port, config_manager=self.config_manager)

        self.model_downloader = ModelDownloader(config_manager=self.config_manager)
        self.embedding_consecutive_crashes = 0
        self.rerank_consecutive_crashes = 0
        self.max_consecutive_crashes = server_cfg.get("auxiliary_max_crashes", 3)

        self._recovery_task: Optional[asyncio.Task] = None
        self._is_running = False

    def _reset_crash_counter_if_ready(self, model_type: str):
        """FR-003: Reset consecutive crash counter when model reaches READY state."""
        if model_type == "embedding" and self.embedding_pm.is_ready():
            self.embedding_consecutive_crashes = 0
        elif model_type == "rerank" and self.rerank_pm.is_ready():
            self.rerank_consecutive_crashes = 0

    async def ensure_embedding_resident(self, model_id: str = "bge-m3", n_ctx: int = 2048) -> ProcessState:
        """FR-006 & FR-002: Ensure BGE-M3 embedding instance is loaded and ready on port 8090."""
        if not self.embedding_enabled:
            return self.embedding_pm.state

        if self.embedding_pm.state.status == ProcessStatusEnum.DISABLED:
            return self.embedding_pm.state

        if self.embedding_pm.is_ready():
            self.embedding_consecutive_crashes = 0
            return self.embedding_pm.state

        # Download if missing
        if not self.model_downloader.is_model_available(model_id):
            print(f"[AuxiliaryManager] Downloading embedding model {model_id}...")
            self.model_downloader.download_model(model_id)

        print(f"[AuxiliaryManager] Spawning embedding instance ({model_id}) on port {self.embedding_port}...")
        state = await self.embedding_pm.spawn_process(model_id=model_id, n_ctx=n_ctx)

        if os.environ.get("MOCK_LLAMA_SERVER"):
            self.embedding_pm.state = ProcessState(
                status=ProcessStatusEnum.READY,
                model_id=model_id,
                port=self.embedding_port,
                vram_offloaded=True,
                vram_offloaded_100pct=True
            )
            self.embedding_consecutive_crashes = 0
            return self.embedding_pm.state

        if state.status == ProcessStatusEnum.READY:
            self.embedding_consecutive_crashes = 0
            return state

        # Poll health if not yet ready
        success = await self._poll_health(self.embedding_port, self.embedding_pm)
        if success:
            self.embedding_consecutive_crashes = 0
        return self.embedding_pm.state

    async def ensure_rerank_resident(self, model_id: str = "bge-reranker-v2-m3", n_ctx: int = 2048) -> ProcessState:
        """FR-006 & FR-002: Ensure BGE-Reranker-v2-M3 instance is loaded and ready on port 8091."""
        if not self.rerank_enabled:
            return self.rerank_pm.state

        if self.rerank_pm.state.status == ProcessStatusEnum.DISABLED:
            return self.rerank_pm.state

        if self.rerank_pm.is_ready():
            self.rerank_consecutive_crashes = 0
            return self.rerank_pm.state

        # Download if missing
        if not self.model_downloader.is_model_available(model_id):
            print(f"[AuxiliaryManager] Downloading reranker model {model_id}...")
            self.model_downloader.download_model(model_id)

        print(f"[AuxiliaryManager] Spawning reranker instance ({model_id}) on port {self.rerank_port}...")
        state = await self.rerank_pm.spawn_process(model_id=model_id, n_ctx=n_ctx)

        if os.environ.get("MOCK_LLAMA_SERVER"):
            self.rerank_pm.state = ProcessState(
                status=ProcessStatusEnum.READY,
                model_id=model_id,
                port=self.rerank_port,
                vram_offloaded=True,
                vram_offloaded_100pct=True
            )
            self.rerank_consecutive_crashes = 0
            return self.rerank_pm.state

        if state.status == ProcessStatusEnum.READY:
            self.rerank_consecutive_crashes = 0
            return state

        # Poll health if not yet ready
        success = await self._poll_health(self.rerank_port, self.rerank_pm)
        if success:
            self.rerank_consecutive_crashes = 0
        return self.rerank_pm.state

    async def _poll_health(self, port: int, pm: ProcessManager, timeout_s: int = 30) -> bool:
        """Poll backend health endpoint until process is ready or times out."""
        start_t = time.perf_counter()
        async with httpx.AsyncClient() as client:
            while time.perf_counter() - start_t < timeout_s:
                if pm.process and pm.process.returncode is not None:
                    pm.state = ProcessState(
                        status=ProcessStatusEnum.ERROR,
                        model_id=pm.state.model_id,
                        port=port,
                        error_message=f"Process exited unexpectedly with code {pm.process.returncode}"
                    )
                    return False

                for endpoint in (f"http://127.0.0.1:{port}/v1/models", f"http://127.0.0.1:{port}/health"):
                    try:
                        resp = await client.get(endpoint, timeout=1.5)
                        if resp.status_code == 200:
                            pm.state = ProcessState(
                                status=ProcessStatusEnum.READY,
                                model_id=pm.state.model_id,
                                port=port,
                                pid=pm.process.pid if pm.process else None,
                                vram_offloaded=True,
                                vram_offloaded_100pct=True
                            )
                            return True
                    except Exception:
                        pass
                await asyncio.sleep(0.5)

        pm.state = ProcessState(
            status=ProcessStatusEnum.ERROR,
            model_id=pm.state.model_id,
            port=port,
            error_message=f"Healthcheck timeout ({timeout_s}s) for port {port}"
        )
        return False

    async def run_sequential_startup(self):
        """FR-004: Sequentially initialize embedding and reranker instances to prevent peak VRAM spikes."""
        try:
            if self.embedding_enabled:
                await self.ensure_embedding_resident("bge-m3")
            if self.rerank_enabled:
                await self.ensure_rerank_resident("bge-reranker-v2-m3")
        except Exception as e:
            print(f"[AuxiliaryManager] Startup warning: {e}")

    async def start_auto_startup_and_recovery(self):
        """FR-004, FR-006 & FR-007: Sequential startup & background crash recovery loop."""
        self._is_running = True
        asyncio.create_task(self.run_sequential_startup())
        self._recovery_task = asyncio.create_task(self._crash_recovery_loop())

    async def check_and_recover_crashes(self):
        """FR-001 & FR-007: Check process states and trigger circuit breaker or recovery."""
        # Check Embedding instance
        if self.embedding_enabled and not os.environ.get("MOCK_LLAMA_SERVER"):
            if self.embedding_pm.state.status != ProcessStatusEnum.DISABLED:
                if self.embedding_pm.state.status in (ProcessStatusEnum.READY, ProcessStatusEnum.LOADING):
                    if self.embedding_pm.process and self.embedding_pm.process.returncode is not None:
                        self.embedding_consecutive_crashes += 1
                        print(f"[AuxiliaryManager] FR-007: Embedding process crash detected! ({self.embedding_consecutive_crashes}/{self.max_consecutive_crashes})")
                        if self.embedding_consecutive_crashes >= self.max_consecutive_crashes:
                            err_msg = f"Embedding disabled due to {self.embedding_consecutive_crashes} consecutive crashes."
                            print(f"[AuxiliaryManager] ❌ FR-001: {err_msg}")
                            self.embedding_pm._log_to_error_log(err_msg)
                            self.embedding_pm.state = ProcessState(
                                status=ProcessStatusEnum.DISABLED,
                                port=self.embedding_port,
                                model_id="bge-m3",
                                error_message=err_msg
                            )
                        else:
                            self.embedding_pm.state = ProcessState(status=ProcessStatusEnum.UNLOADED, port=self.embedding_port)
                            await self.ensure_embedding_resident("bge-m3")
                elif self.embedding_pm.state.status == ProcessStatusEnum.READY:
                    self._reset_crash_counter_if_ready("embedding")

        # Check Rerank instance
        if self.rerank_enabled and not os.environ.get("MOCK_LLAMA_SERVER"):
            if self.rerank_pm.state.status != ProcessStatusEnum.DISABLED:
                if self.rerank_pm.state.status in (ProcessStatusEnum.READY, ProcessStatusEnum.LOADING):
                    if self.rerank_pm.process and self.rerank_pm.process.returncode is not None:
                        self.rerank_consecutive_crashes += 1
                        print(f"[AuxiliaryManager] FR-007: Reranker process crash detected! ({self.rerank_consecutive_crashes}/{self.max_consecutive_crashes})")
                        if self.rerank_consecutive_crashes >= self.max_consecutive_crashes:
                            err_msg = f"Reranker disabled due to {self.rerank_consecutive_crashes} consecutive crashes."
                            print(f"[AuxiliaryManager] ❌ FR-001: {err_msg}")
                            self.rerank_pm._log_to_error_log(err_msg)
                            self.rerank_pm.state = ProcessState(
                                status=ProcessStatusEnum.DISABLED,
                                port=self.rerank_port,
                                model_id="bge-reranker-v2-m3",
                                error_message=err_msg
                            )
                        else:
                            self.rerank_pm.state = ProcessState(status=ProcessStatusEnum.UNLOADED, port=self.rerank_port)
                            await self.ensure_rerank_resident("bge-reranker-v2-m3")
                elif self.rerank_pm.state.status == ProcessStatusEnum.READY:
                    self._reset_crash_counter_if_ready("rerank")


    async def _crash_recovery_loop(self):
        """FR-007: Background crash recovery loop auto-restarting failed instances."""
        while self._is_running:
            await asyncio.sleep(5.0)
            await self.check_and_recover_crashes()

    async def shutdown(self):
        """Gracefully stop embedding and reranker instances on server shutdown."""
        self._is_running = False
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()

        await self.embedding_pm.stop_process()
        await self.rerank_pm.stop_process()


# Singleton instance
auxiliary_manager = AuxiliaryModelManager()
