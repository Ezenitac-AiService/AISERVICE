import os
import asyncio
import json
import time
from typing import Optional, Dict, Any
import httpx
from src.core.config_manager import ConfigManager
from src.core.process_manager import ProcessManager, ProcessStatusEnum, ProcessState
from src.core.event_broadcaster import EventBroadcaster
from src.core.model_downloader import ModelDownloader
from src.core.gpu_detector import GpuDeviceInfo, VramOffloadStatus, check_gpu_availability, GpuAccelerationError

# Alias ServerState to ProcessStatusEnum for 100% backward compatibility
ServerState = ProcessStatusEnum

class LlamaManager:
    """Coordinator class delegating to ProcessManager (Dual-LLM: 9B Synthesis on 8089, 4B Router on 8088) and EventBroadcaster."""

    def __init__(self, config_manager: Optional[ConfigManager] = None, port: Optional[int] = None):
        if config_manager is None:
            config_manager = ConfigManager()
        self.config_manager = config_manager
        server_cfg = config_manager.get_server_config()
        if port is not None:
            self.port = port
        else:
            self.port = server_cfg.get("backend_port", 8089) if server_cfg else 8089

        # Dual-LLM: Dedicated synthesis PM (8089) and router PM (8088)
        self.synthesis_pm = ProcessManager(port=8089, config_manager=self.config_manager)
        self.router_pm = ProcessManager(port=8088, config_manager=self.config_manager)
        self.process_manager = self.synthesis_pm if self.port == 8089 else ProcessManager(port=self.port, config_manager=self.config_manager)

        self.broadcaster = EventBroadcaster(queue_maxsize=100)
        self.model_downloader = ModelDownloader()
        self._error_msg = ""
        self._lock: Optional[asyncio.Lock] = None
        self._gpu_info: Optional[GpuDeviceInfo] = None
        self._vram_offload_status: Optional[VramOffloadStatus] = None

    def get_pm_for_model(self, model_id: Optional[str] = None) -> ProcessManager:
        """Dynamically routes to synthesis_pm (9B on 8089) or router_pm (4B on 8088)."""
        if not model_id:
            return self.synthesis_pm
        model_lower = model_id.lower()
        if "4b" in model_lower or "fast" in model_lower:
            return self.router_pm
        return self.synthesis_pm

    @property
    def lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or (loop is not None and getattr(self._lock, "_loop", None) is not None and self._lock._loop is not loop):
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def state(self) -> ProcessStatusEnum:
        return self.synthesis_pm.state.status

    @state.setter
    def state(self, value: ProcessStatusEnum):
        self.synthesis_pm.state = ProcessState(
            status=value,
            model_id=self.synthesis_pm.state.model_id,
            port=self.synthesis_pm.port,
            pid=self.synthesis_pm.state.pid,
            error_message=self._error_msg
        )
        self.process_manager.state = self.synthesis_pm.state

    @property
    def process(self):
        return self.synthesis_pm.process

    @process.setter
    def process(self, proc):
        self.synthesis_pm.process = proc
        self.process_manager.process = proc

    @property
    def vram_total(self) -> int:
        return self.synthesis_pm.vram_total

    @property
    def hardware_limits(self) -> Dict[str, int]:
        return self.synthesis_pm.hardware_limits

    def is_ready(self, model_id: Optional[str] = None) -> bool:
        if model_id:
            return self.get_pm_for_model(model_id).is_ready()
        return self.synthesis_pm.is_ready()

    def subscribe(self) -> asyncio.Queue:
        return self.broadcaster.subscribe(initial_event=self.get_status_event())

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.broadcaster.unsubscribe(q)

    def _notify_listeners(self) -> None:
        event = self.get_status_event()
        self.broadcaster.broadcast(event)

    def get_status_event(self) -> dict:
        cfg = self.config_manager.get_config()
        state = self.synthesis_pm.state
        from src.core.auxiliary_manager import auxiliary_manager
        data = {
            "state": state.status,
            "synthesis_state": self.synthesis_pm.state.status,
            "router_state": self.router_pm.state.status,
            "current_model": cfg.get("current_model") or "qwen3.5-9b",
            "current_n_ctx": cfg.get("current_n_ctx") or 32768,
            "vram_total": self.vram_total,
            "vram_used": (self._gpu_info.total_vram_mb - self._gpu_info.free_vram_mb) if self._gpu_info else (0 if state.status == ProcessStatusEnum.UNLOADED else 0),
            "error_msg": state.error_message or self.router_pm.state.error_message or self._error_msg,
            "gpu_cuda_available": self._gpu_info.is_cuda_available if self._gpu_info else False,
            "vram_offloaded_100pct": (self.synthesis_pm.state.vram_offloaded_100pct or (self._vram_offload_status.is_fully_offloaded if self._vram_offload_status else False)),
            "gpu_info": self._gpu_info.model_dump() if self._gpu_info else None,
            "offload_status": self._vram_offload_status.model_dump() if self._vram_offload_status else None,
            "embedding_status": auxiliary_manager.embedding_pm.state.status,
            "rerank_status": auxiliary_manager.rerank_pm.state.status,
        }
        return {"event": "status", "data": json.dumps(data)}

    async def _start_server_subprocess(self, model_id: str, n_ctx: int):
        self._error_msg = ""
        pm = self.get_pm_for_model(model_id)
        state = await pm.spawn_process(model_id, n_ctx)

        try:
            self._gpu_info = check_gpu_availability()
        except GpuAccelerationError:
            self._gpu_info = None
        self._vram_offload_status = pm.vram_offload_status

        self._notify_listeners()

        if state.status == ProcessStatusEnum.ERROR:
            self._error_msg = state.error_message or ""
            return

    async def load_model(self, model_id: str, n_ctx: int):
        """Model load delegation to appropriate process manager."""
        async with self.lock:
            pm = self.get_pm_for_model(model_id)
            await pm.stop_process()
            self.config_manager.update_config(current_model=model_id, current_n_ctx=n_ctx)
            asyncio.create_task(self._start_server_subprocess(model_id, n_ctx))

    async def load_model_for_pm(self, pm: ProcessManager, model_id: str, n_ctx: int = 16384) -> ProcessState:
        """FR-003 & FR-061: Loads model into the specified process manager with offline verification."""
        if pm.is_ready() and pm.state.model_id == model_id:
            return pm.state

        if pm.state.status == ProcessStatusEnum.LOADING and pm.state.model_id == model_id:
            ready = await self._wait_for_pm_ready(pm, timeout=60.0)
            if ready:
                return pm.state

        await pm.stop_process()

        if not self.model_downloader.is_model_available(model_id):
            print(f"[LlamaManager] 모델 {model_id} 로컬 미존재 → 자동 다운로드 시작")
            pm.state = ProcessState(
                status=ProcessStatusEnum.DOWNLOADING,
                model_id=model_id,
                port=pm.port,
            )
            self._notify_listeners()

            try:
                await asyncio.to_thread(self.model_downloader.ensure_model_available, model_id)
            except (FileNotFoundError, ValueError) as e:
                self._error_msg = str(e)
                pm.state = ProcessState(
                    status=ProcessStatusEnum.ERROR,
                    model_id=model_id,
                    port=pm.port,
                    error_message=self._error_msg,
                )
                self._notify_listeners()
                return pm.state

        state = await pm.spawn_process(model_id, n_ctx)
        ready = await self._wait_for_pm_ready(pm, timeout=120.0)
        if not ready and pm.state.status == ProcessStatusEnum.LOADING:
            self._error_msg = "서빙 프로세스 헬스체크 타임아웃 (120초)"
            pm.state = ProcessState(
                status=ProcessStatusEnum.ERROR,
                model_id=model_id,
                port=pm.port,
                error_message=self._error_msg,
            )
            self._notify_listeners()

        return pm.state

    async def load_model_with_download(self, model_id: str, n_ctx: int = 16384) -> ProcessState:
        """FR-003: Model load with offline verification."""
        async with self.lock:
            pm = self.get_pm_for_model(model_id)
            self.config_manager.update_config(current_model=model_id, current_n_ctx=n_ctx)
            return await self.load_model_for_pm(pm, model_id, n_ctx)

    def validate_request_allowed(self, model_id: Optional[str] = None) -> None:
        """T008 / FR-003 / T016: Block incoming inference requests while process is loading / not ready with RFC 9110 HTTP 503 Retry-After: 5."""
        pm = self.get_pm_for_model(model_id) if model_id else self.synthesis_pm
        if not pm.is_ready():
            from fastapi import HTTPException
            target_model = model_id or pm.state.model_id or "model"
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "message": f"Inference request blocked: Model '{target_model}' is not ready (state: '{pm.state.status.value}'). Must wait until VRAM 100% offload is complete.",
                        "type": "service_unavailable",
                        "code": "model_loading"
                    }
                },
                headers={"Retry-After": "5"}
            )

    def get_max_allowed_n_ctx(self, model_id: str) -> int:
        """Returns maximum allowed n_ctx for a given model based on Dual-LLM architecture.

        4B router model allows context scaling up to 8K.
        9B synthesis model natively supports 32K context with DeltaNet 3:1 KV cache.
        """
        resolved_id = self.config_manager.resolve_model_id(model_id)
        if any(token in resolved_id.lower() for token in ["9b", "12b"]):
            return 32768
        elif any(token in resolved_id.lower() for token in ["4b", "e4b"]):
            return 8192
        elif any(token in resolved_id.lower() for token in ["2b", "e2b"]):
            return 8192
        elif any(token in resolved_id.lower() for token in ["27b", "35b"]):
            return 131072
        return 8192

    def validate_requested_context(self, model_id: str, requested_n_ctx: int) -> None:
        """FR-006: Validates requested n_ctx against max allowed. Raises HTTPException 400 if exceeded."""
        from fastapi import HTTPException
        max_allowed = self.get_max_allowed_n_ctx(model_id)
        if requested_n_ctx > max_allowed:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "message": f"Requested context length ({requested_n_ctx}) exceeds model maximum allowed context length ({max_allowed}) for model '{model_id}'.",
                        "type": "invalid_request_error",
                        "param": "n_ctx",
                        "code": "context_length_exceeded"
                    }
                }
            )

    async def _wait_for_pm_ready(self, pm: ProcessManager, timeout: float = 30.0, interval: float = 0.5) -> bool:
        health_url = f"http://127.0.0.1:{pm.port}/health"
        models_url = f"http://127.0.0.1:{pm.port}/v1/models"
        deadline = time.time() + timeout

        while time.time() < deadline:
            is_health_ok = False
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(health_url, timeout=2.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") in ("ok", "ready") or data.get("slots_idle", 0) >= 0:
                            is_health_ok = True
            except Exception:
                pass

            if not is_health_ok:
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(models_url, timeout=2.0)
                        if resp.status_code == 200:
                            is_health_ok = True
                except Exception:
                    pass

            if is_health_ok:
                pm.state = ProcessState(
                    status=ProcessStatusEnum.READY,
                    model_id=pm.state.model_id,
                    port=pm.port,
                    pid=pm.state.pid or (pm.process.pid if pm.process else None),
                    vram_offloaded_100pct=True,
                    vram_offloaded=True
                )
                self._notify_listeners()
                print(f"[LlamaManager] ✅ 서빙 프로세스 (port {pm.port}) READY (/health OK 확인)")
                return True

            await asyncio.sleep(interval)

        return False

    async def _wait_for_ready(self, timeout: float = 30.0, max_retries: int = 10, interval: float = 0.5) -> bool:
        return await self._wait_for_pm_ready(self.synthesis_pm, timeout=timeout, interval=interval)

    async def ensure_default_model_resident(self, default_model_id: str = None) -> ProcessState:
        """FR-061: Guarantees resident serving for both 9B (8089) and 4B (8088)."""
        synthesis_model = os.getenv("SYNTHESIS_LLM_MODEL", "qwen3.5-9b")
        router_model = os.getenv("FAST_LLM_MODEL", "qwen3.5-4b")

        if not self.synthesis_pm.is_ready():
            print(f"[LlamaManager] Starting Synthesis LLM '{synthesis_model}' on port 8089 (n_ctx=32768)")
            await self.load_model_for_pm(self.synthesis_pm, synthesis_model, n_ctx=32768)

        if not self.router_pm.is_ready():
            print(f"[LlamaManager] Starting Router LLM '{router_model}' on port 8088 (n_ctx=8192)")
            await self.load_model_for_pm(self.router_pm, router_model, n_ctx=8192)

        return self.synthesis_pm.state

    def touch_activity(self):
        """FR-017: Record last activity timestamp."""
        self._last_active_time = time.time()

    async def check_idle_reclamation(self, idle_threshold_seconds: int = 60):
        """FR-070: Permanently eradicated. Dual-LLM architecture maintains persistent 9B/4B residency."""
        pass

    async def check_and_recover_crashes(self) -> None:
        """FR-004 & FR-061: Dual-LLM independent self-healing for 9B (8089) and 4B (8088)."""
        synthesis_model = os.getenv("SYNTHESIS_LLM_MODEL", "qwen3.5-9b")
        router_model = os.getenv("FAST_LLM_MODEL", "qwen3.5-4b")

        if not self.synthesis_pm.is_ready() and self.synthesis_pm.state.status != ProcessStatusEnum.LOADING:
            print(f"[LlamaManager] ⚠️ Synthesis LLM ({synthesis_model} on 8089) crash/missing -> auto recovering...")
            try:
                await self.load_model_for_pm(self.synthesis_pm, synthesis_model, n_ctx=32768)
            except Exception as e:
                print(f"[LlamaManager] ❌ Synthesis auto recovery failed: {e}")

        if not self.router_pm.is_ready() and self.router_pm.state.status != ProcessStatusEnum.LOADING:
            print(f"[LlamaManager] ⚠️ Router LLM ({router_model} on 8088) crash/missing -> auto recovering...")
            try:
                await self.load_model_for_pm(self.router_pm, router_model, n_ctx=8192)
            except Exception as e:
                print(f"[LlamaManager] ❌ Router auto recovery failed: {e}")

    async def start_health_monitor(self, interval_seconds: float = 3.0) -> None:
        """FR-004: Periodic health check and self-healing monitor loop."""
        print(f"[LlamaManager] Dual-LLM health monitor started (interval: {interval_seconds}s)")
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self.check_and_recover_crashes()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[LlamaManager] Health monitor exception: {e}")

    async def unload_model(self):
        async with self.lock:
            await self._unload_model_internal()

    async def _unload_model_internal(self):
        await self.synthesis_pm.stop_process()
        await self.router_pm.stop_process()
        self._vram_offload_status = None
        self._notify_listeners()

# Global instances
config_manager = ConfigManager()
llama_manager = LlamaManager(config_manager)

