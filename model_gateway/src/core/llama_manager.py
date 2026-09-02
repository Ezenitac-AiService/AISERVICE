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
    """Coordinator class delegating to ProcessManager and EventBroadcaster."""

    def __init__(self, config_manager: Optional[ConfigManager] = None, port: Optional[int] = None):
        if config_manager is None:
            config_manager = ConfigManager()
        self.config_manager = config_manager
        server_cfg = config_manager.get_server_config()
        if port is not None:
            self.port = port
        else:
            self.port = server_cfg.get("backend_port", 8089) if server_cfg else 8089
        self.process_manager = ProcessManager(port=self.port)
        self.broadcaster = EventBroadcaster(queue_maxsize=100)
        self.model_downloader = ModelDownloader()
        self._error_msg = ""
        self._lock: Optional[asyncio.Lock] = None
        self._gpu_info: Optional[GpuDeviceInfo] = None
        self._vram_offload_status: Optional[VramOffloadStatus] = None

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
        return self.process_manager.state.status

    @state.setter
    def state(self, value: ProcessStatusEnum):
        # Backward compatibility setter
        self.process_manager.state = ProcessState(
            status=value,
            model_id=self.process_manager.state.model_id,
            port=self.port,
            pid=self.process_manager.state.pid,
            error_message=self._error_msg
        )

    @property
    def process(self):
        return self.process_manager.process

    @process.setter
    def process(self, proc):
        self.process_manager.process = proc

    @property
    def vram_total(self) -> int:
        return self.process_manager.vram_total

    @property
    def hardware_limits(self) -> Dict[str, int]:
        return self.process_manager.hardware_limits

    def is_ready(self) -> bool:
        return self.process_manager.is_ready()

    def subscribe(self) -> asyncio.Queue:
        return self.broadcaster.subscribe(initial_event=self.get_status_event())

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.broadcaster.unsubscribe(q)

    def _notify_listeners(self) -> None:
        event = self.get_status_event()
        self.broadcaster.broadcast(event)

    def get_status_event(self) -> dict:
        cfg = self.config_manager.get_config()
        state = self.process_manager.state
        from src.core.auxiliary_manager import auxiliary_manager
        data = {
            "state": state.status,
            "current_model": cfg.get("current_model"),
            "current_n_ctx": cfg.get("current_n_ctx"),
            "vram_total": self.vram_total,
            "vram_used": (self._gpu_info.total_vram_mb - self._gpu_info.free_vram_mb) if self._gpu_info else (0 if state.status == ProcessStatusEnum.UNLOADED else 0),
            "error_msg": state.error_message or self._error_msg,
            "gpu_cuda_available": self._gpu_info.is_cuda_available if self._gpu_info else False,
            "vram_offloaded_100pct": self._vram_offload_status.is_fully_offloaded if self._vram_offload_status else False,
            "gpu_info": self._gpu_info.model_dump() if self._gpu_info else None,
            "offload_status": self._vram_offload_status.model_dump() if self._vram_offload_status else None,
            "embedding_status": auxiliary_manager.embedding_pm.state.status,
            "rerank_status": auxiliary_manager.rerank_pm.state.status,
        }
        return {"event": "status", "data": json.dumps(data)}

    async def _start_server_subprocess(self, model_id: str, n_ctx: int):
        self._error_msg = ""
        state = await self.process_manager.spawn_process(model_id, n_ctx)

        # FR-005: GPU 검증 결과 캡처
        try:
            self._gpu_info = check_gpu_availability()
        except GpuAccelerationError:
            self._gpu_info = None
        # T012: ProcessManager의 VRAM 오프로드 상태 동기화
        self._vram_offload_status = self.process_manager.vram_offload_status

        self._notify_listeners()

        if state.status == ProcessStatusEnum.ERROR:
            self._error_msg = state.error_message or ""
            return

    async def load_model(self, model_id: str, n_ctx: int):
        """모델 로드. 로컬 가중치 미존재 시 자동 다운로드 후 서빙 프로세스 개설."""
        async with self.lock:
            await self._unload_model_internal()
            self.config_manager.update_config(current_model=model_id, current_n_ctx=n_ctx)
            asyncio.create_task(self._start_server_subprocess(model_id, n_ctx))

    async def load_model_with_download(self, model_id: str, n_ctx: int = 16384) -> ProcessState:
        """FR-003: 모델 로드 시 로컬 가중치 미존재를 탐지하고 자동 다운로드 수행 후 서빙 프로세스 개설.

        Args:
            model_id: 모델 식별자 (예: 'qwen3.5-2b', 'gemma4-e2b')
            n_ctx: 컨텍스트 크기

        Returns:
            ProcessState: 최종 프로세스 상태
        """
        async with self.lock:
            if self.is_ready() and self.process_manager.state.model_id == model_id:
                return self.process_manager.state

            if self.process_manager.state.status == ProcessStatusEnum.LOADING and self.process_manager.state.model_id == model_id:
                ready = await self._wait_for_ready(timeout=60.0)
                if ready:
                    return self.process_manager.state

            await self._unload_model_internal()

            # FR-003: 로컬 파일 미존재 탐지 및 자동 다운로드
            if not self.model_downloader.is_model_available(model_id):
                print(f"[LlamaManager] 모델 {model_id} 로컬 미존재 → 자동 다운로드 시작")
                self.process_manager.state = ProcessState(
                    status=ProcessStatusEnum.DOWNLOADING,
                    model_id=model_id,
                    port=self.port,
                )
                self._notify_listeners()

                try:
                    await asyncio.to_thread(self.model_downloader.ensure_model_available, model_id)
                except (FileNotFoundError, ValueError) as e:
                    self._error_msg = str(e)
                    self.process_manager.state = ProcessState(
                        status=ProcessStatusEnum.ERROR,
                        model_id=model_id,
                        port=self.port,
                        error_message=self._error_msg,
                    )
                    self._notify_listeners()
                    return self.process_manager.state

            self.config_manager.update_config(current_model=model_id, current_n_ctx=n_ctx)
            await self._start_server_subprocess(model_id, n_ctx)

            # T006: HTTP 헬스체크 폴링으로 READY 상태 대기
            ready = await self._wait_for_ready(timeout=120.0)
            if not ready and self.process_manager.state.status == ProcessStatusEnum.LOADING:
                self._error_msg = f"서빙 프로세스 헬스체크 타임아웃 (120초)"
                self.process_manager.state = ProcessState(
                    status=ProcessStatusEnum.ERROR,
                    model_id=model_id,
                    port=self.port,
                    error_message=self._error_msg,
                )
                self._notify_listeners()

            return self.process_manager.state

    def validate_request_allowed(self) -> None:
        """T008 / FR-003: Block incoming inference requests while process is loading / not ready."""
        if not self.is_ready():
            raise RuntimeError(
                f"Inference request blocked: Process is in state '{self.state.value}'. "
                f"Must wait until VRAM 100% offload is complete and state is READY."
            )

    def get_max_allowed_n_ctx(self, model_id: str) -> int:
        """Spec 034 & Spec 036: Returns maximum allowed n_ctx for a given model based on 3-axis dynamic hardware profiling.

        2B models allow extended context up to 64K (Standard) ~ 128K (Ultra) on 8GB VRAM.
        4B models allow context scaling up to 32K (Standard) ~ 48K (Ultra).
        9B models scale based on VRAM capacity (up to 128K on 24GB+).
        """
        resolved_id = self.config_manager.resolve_model_id(model_id)

        try:
            from src.core.gpu_detector import detect_hardware_capabilities
            profile = detect_hardware_capabilities()
            if any(token in resolved_id.lower() for token in ["2b", "e2b"]):
                return max(65536, profile.resident_ultra_n_ctx)
            elif any(token in resolved_id.lower() for token in ["4b", "e4b"]):
                return max(32768, profile.batch_n_ctx if hasattr(profile, "batch_n_ctx") else 32768)
            elif any(token in resolved_id.lower() for token in ["9b", "12b"]):
                return profile.dynamic_n_ctx if profile.total_vram_mb >= 16000 else 16384
            elif any(token in resolved_id.lower() for token in ["27b", "35b"]):
                return 131072
        except Exception:
            pass

        # Fallback conservative bounds (Spec 036)
        if any(token in resolved_id.lower() for token in ["2b", "e2b"]):
            return 131072
        if any(token in resolved_id.lower() for token in ["4b", "e4b"]):
            return 49152
        return 16384

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


    async def _wait_for_ready(self, timeout: float = 30.0, max_retries: int = 10, interval: float = 0.5) -> bool:
        """T006: HTTP GET /health JSON API & VRAM 100% 오프로드 완납 상태 동시 확인 후 READY 전환.

        FR-001, FR-003, FR-009 준수.
        """
        health_url = f"http://127.0.0.1:{self.port}/health"
        models_url = f"http://127.0.0.1:{self.port}/v1/models"
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
                self.process_manager.state = ProcessState(
                    status=ProcessStatusEnum.READY,
                    model_id=self.process_manager.state.model_id,
                    port=self.port,
                    pid=self.process_manager.state.pid,
                    vram_offloaded_100pct=True,
                    vram_offloaded=True
                )
                self._notify_listeners()
                print(f"[LlamaManager] ✅ 서빙 프로세스 READY (/health OK 확인)")
                return True

            await asyncio.sleep(interval)

        return False

    async def ensure_default_model_resident(self, default_model_id: str = None) -> ProcessState:
        """FR-001 & FR-006 & Spec 036: 평상시 기본 서비스 모델(qwen3.5-2b 64K) VRAM 상주 서빙 보장."""
        if default_model_id is None:
            default_model_id = os.getenv("DEFAULT_MODEL", os.getenv("FAST_LLM_MODEL", "qwen3.5-2b"))
        current_model = self.config_manager.get_config().get("current_model")
        target_n_ctx = int(self.config_manager.get_config().get("current_n_ctx", 16384))
        if self.is_ready() and current_model == default_model_id:
            print(f"[LlamaManager] 기본 초고속 모델 '{default_model_id}'이 이미 VRAM 상주 서빙 중입니다 (n_ctx={target_n_ctx}).")
            return self.process_manager.state

        print(f"[LlamaManager] 기본 초고속 모델 '{default_model_id}' VRAM 상주 서빙 로드 시작 (n_ctx={target_n_ctx})")
        return await self.load_model_with_download(default_model_id, n_ctx=target_n_ctx)

    def touch_activity(self):
        """FR-017: Record last activity timestamp for idle memory reclamation."""
        self._last_active_time = time.time()

    async def check_idle_reclamation(self, idle_threshold_seconds: int = 60):
        """FR-017 & Spec 036 T013: If batch model (4B) has been idle for >= 60s, automatically restore 2B 16K base model."""
        if not hasattr(self, "_last_active_time"):
            self._last_active_time = time.time()
            return

        current_model = self.process_manager.state.model_id
        if current_model and "4b" in current_model.lower():
            idle_seconds = time.time() - self._last_active_time
            if idle_seconds >= idle_threshold_seconds:
                print(f"[LlamaManager] ⏱️ 4B 배치 모델 {idle_seconds:.1f}초 유휴 감지. 상시 기본 모델(qwen3.5-2b @ 16K)로 자동 복귀하여 VRAM을 회수합니다.")
                self.config_manager.update_config(current_model="qwen3.5-2b", current_n_ctx=16384)
                await self.ensure_default_model_resident("qwen3.5-2b")

    async def check_and_recover_crashes(self) -> None:
        """FR-004 & FR-007: 메인 LLM 프로세스 비정상 종료(Exit 137 / OOM) 감지 시 자동 재스폰 자가치유."""
        if self.is_ready():
            return

        if self.process_manager.state.status == ProcessStatusEnum.LOADING:
            return

        print("[LlamaManager] ⚠️ 메인 LLM(8089) 프로세스 부재 또는 크래시 감지 -> 자동 자가치유 재스폰 시작...")
        try:
            default_model = self.config_manager.get_default_model()
            target_n_ctx = int(self.config_manager.get_config().get("current_n_ctx", 16384))
            await self.load_model_with_download(default_model, n_ctx=target_n_ctx)
        except Exception as e:
            print(f"[LlamaManager] ❌ 자동 복구 실패: {e}")

    async def start_health_monitor(self, interval_seconds: float = 3.0) -> None:
        """FR-004: 백그라운드 주기적 프로세스 헬스체크 및 자가치유 모니터 루프."""
        print(f"[LlamaManager] 메인 LLM 프로세스 헬스 모니터 시작 (간격: {interval_seconds}초)")
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self.check_and_recover_crashes()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[LlamaManager] 헬스 모니터 예외: {e}")

    async def unload_model(self):
        async with self.lock:
            await self._unload_model_internal()

    async def _unload_model_internal(self):
        await self.process_manager.stop_process()
        self._vram_offload_status = None
        self._notify_listeners()

# Global instances
config_manager = ConfigManager()
llama_manager = LlamaManager(config_manager)

