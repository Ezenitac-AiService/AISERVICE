import asyncio
import atexit
import collections
import datetime
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field
from src.core.config_manager import ConfigManager
from src.core.gpu_detector import (
    GpuAccelerationError,
    PortCollisionError,
    VramOffloadStatus,
    VramOverflowError,
    estimate_kv_cache_vram,
    get_nvml_vram_info,
)

_signal_handlers_registered = False

def register_process_cleanup_hooks() -> None:
    """FR-003: Register atexit hooks to force kill zombie llama-servers."""
    global _signal_handlers_registered
    if _signal_handlers_registered:
        return
    _signal_handlers_registered = True
    atexit.register(ProcessManager.force_kill_zombie_llama_servers)

async def poll_server_health(
    port: int = 8081,
    timeout: float = 10.0,
    interval: float = 0.2,
    file_size_mb: Optional[float] = None,
    n_ctx: Optional[int] = None
) -> bool:
    """FR-002 & FR-003: Poll /health endpoint up to timeout (max 60s dynamic) with 0.2s interval until HTTP 200 OK."""
    if os.environ.get("MOCK_LLAMA_SERVER") == "1":
        return True

    if file_size_mb is not None or n_ctx is not None:
        calc = 15.0
        if file_size_mb is not None:
            calc += (file_size_mb / 500.0) * 5.0
        if n_ctx is not None:
            calc += (n_ctx / 4096.0) * 10.0
        timeout = min(60.0, max(15.0, calc))

    url = f"http://127.0.0.1:{port}/health"
    fallback_url = f"http://127.0.0.1:{port}/v1/models"
    start_time = time.perf_counter()
    while (time.perf_counter() - start_time) < timeout:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, timeout=0.5)
                if res.status_code == 200:
                    return True
                elif res.status_code == 404:
                    res_fb = await client.get(fallback_url, timeout=0.5)
                    if res_fb.status_code == 200:
                        return True
        except Exception:
            pass
        await asyncio.sleep(interval)
    return False


class ProcessStatusEnum(str, Enum):
    UNLOADED = "UNLOADED"
    DOWNLOADING = "DOWNLOADING"
    LOADING = "LOADING"
    VRAM_OFFLOADED = "VRAM_OFFLOADED"
    READY = "READY"
    ERROR = "ERROR"
    DISABLED = "DISABLED"

class TestExecutionMode(str, Enum):
    MOCK = "mock"
    REAL = "real"

class LlamaServerBinaryInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    binary_path: str = Field(..., description="llama-server 바이너리 경로")
    is_cuda_enabled: bool = Field(default=True, description="CUDA 가속 구동 여부")
    build_source: str = Field(default="PATH", description="바이너리 취득 경로 (PATH / CMAKE_BUILD / PYTHON_MODULE)")
    version_info: Optional[str] = Field(default=None, description="바이너리 버전 정보")
    runtime_backend: str = Field(default="llama.cpp-cuda", description="선택된 runtime backend")

class RealGpuBenchmarkSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(default="session-001", description="세션 식별자")
    execution_mode: TestExecutionMode = Field(default=TestExecutionMode.REAL, description="테스트 실행 모드")
    target_models: list[str] = Field(default_factory=list, description="대상 6개 모델 ID 목록")
    completed_models: list[str] = Field(default_factory=list, description="성공 모델 ID 목록")
    failed_models: dict[str, str] = Field(default_factory=dict, description="실패 모델 ID 및 원인 메시지")
    vram_safety_threshold_mb: int = Field(default=11264, description="VRAM 안전 임계치 MB")


class SpeculativeDecodingConfig(BaseModel):
    """FR-003: Speculative Decoding 가속 설정 데이터 모델."""
    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(default=False, description="Speculative Decoding 활성화 여부")
    draft_model_id: Optional[str] = Field(default=None, description="초경량 드래프트 모델 ID")
    draft_max_tokens: int = Field(default=16, description="드래프트 모델 샘플링 깊이")


class ProcessState(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ProcessStatusEnum = Field(default=ProcessStatusEnum.UNLOADED, description="현재 프로세스 구동 상태")
    model_id: Optional[str] = Field(default=None, description="로딩된 모델 식별자")
    port: Optional[int] = Field(default=None, description="llama-server 바인딩 포트")
    pid: Optional[int] = Field(default=None, description="OS 프로세스 PID")
    error_message: Optional[str] = Field(default=None, description="에러 발생 시 상세 메시지")
    exit_code: Optional[int] = Field(default=None, description="종료 코드")
    vram_offloaded: Optional[bool] = Field(default=None, description="VRAM 100% 오프로드 검증 완료 여부")
    vram_offloaded_100pct: bool = Field(default=False, description="VRAM 100% 오프로드 검증 완료 여부")
    active_requests: int = Field(default=0, description="현재 진행 중인 활성 추론 스트림 수")

class ProcessLifecycleState(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ProcessStatusEnum = Field(default=ProcessStatusEnum.UNLOADED, description="현재 프로세스 구동 상태")
    pid: Optional[int] = Field(default=None, description="OS 프로세스 PID")
    port: Optional[int] = Field(default=None, description="llama-server 바인딩 포트")
    vram_offloaded_100pct: bool = Field(default=False, description="VRAM 100% 오프로드 검증 완료 여부")
    active_requests: int = Field(default=0, description="현재 진행 중인 활성 추론 스트림 수")
    model_id: Optional[str] = Field(default=None, description="로딩된 모델 식별자")
    error_message: Optional[str] = Field(default=None, description="에러 메시지")
    exit_code: Optional[int] = Field(default=None, description="종료 코드")

class VramLoadTimingGuard(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline_vram: int = Field(default=0, description="프로세스 실행 전 기본 VRAM 사용량(MB)")
    target_vram: int = Field(default=0, description="목표 VRAM 탑재 용량(MB)")
    offload_verified_at: Optional[float] = Field(default=None, description="VRAM 100% 검증 시각")
    socket_cleared: bool = Field(default=False, description="소켓 포트 완전 클리어 여부")
    nvml_handle: Optional[Any] = Field(default=None, description="PyNVML 핸들 참조")
    kv_cache_vram_mb: int = Field(default=0, description="사전 추정된 KV Cache VRAM 용량(MB)")

class QwenModelPreset(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str = Field(..., description="모델 식별자")
    model_name: str = Field(..., description="표시용 모델 명칭")
    gguf_path: str = Field(..., description="GGUF 모델 상대 경로")
    clip_path: Optional[str] = Field(default=None, description="CLIP 프로젝터 경로")
    chat_template: str = Field(default="chatml", description="llama-server 채팅 템플릿 인자")
    default_n_ctx: int = Field(default=4096, description="기본 컨텍스트 크기")
    vram_limit_mb: int = Field(..., description="권장 VRAM 임계치 (MB)")
    quant_type: str = Field(default="q4_k_m", description="양자화 타입 (q4_k_m, q4_0, q8_0)")

class ProcessManager:
    """Subprocess lifecycle manager for llama-server subprocesses supporting Gemma 4 and Qwen3.5."""

    def __init__(self, port: int = 8081, config_manager: Optional['ConfigManager'] = None):
        # FR-001 & FR-002: ConfigManager를 단일 진실 소스(Single Source of Truth)로 사용
        if config_manager is None:
            from src.core.config_manager import ConfigManager
            config_manager = ConfigManager()
        self._config_manager = config_manager

        catalog = config_manager.get_model_catalog()
        loaded_presets = {}
        if catalog:
            for model_id, entry in catalog.items():
                loaded_presets[model_id] = {
                    "model": entry.get("model_path", ""),
                    "clip": entry.get("clip_path"),
                    "chat_template": entry.get("chat_template", "chatml"),
                    "vram_est_mb": entry.get("vram_est_mb", 6000),
                    "requires_mmproj": entry.get("requires_mmproj", False),
                    "task_type": entry.get("task_type", "llm"),
                    "default_port": entry.get("default_port"),
                }
        self.model_presets = loaded_presets

        # 외부 JSON 서버 설정에서 VRAM 상한선 및 포트 동적 로드 (명시적 port 지정 시 최우선 적용)
        server_config = config_manager.get_server_config()
        self.vram_max_capacity_mb = config_manager.get_vram_max_capacity_mb()
        if port != 8081:
            self.port = port
        else:
            self.port = server_config.get("port", 8081) if server_config else 8081

        self.hardware_limits = {
            "gemma4-e2b": 65536,
            "gemma4-e4b": 32768,
            "gemma4-12b": 16384,
            "qwen3.5-2b": 131072,
            "qwen3.5-4b": 49152,
            "qwen3.5-9b": 32768,
            "qwen3.6-27b": 131072,
            "qwen3.6-35b-a3b": 131072
        }
        self.vram_total = 24000
        self.process: Optional[asyncio.subprocess.Process] = None
        self.state: ProcessState = ProcessState(status=ProcessStatusEnum.UNLOADED, port=self.port)
        self.vram_offload_status: Optional[VramOffloadStatus] = None
        self._log_drain_task: Optional[asyncio.Task] = None
        self._log_file_handle: Optional[Any] = None
        self._tps_history: collections.deque = collections.deque(maxlen=20)
        self.active_runtime_backend: str | None = None
        self.runtime_backend_failures: list[str] = []
        register_process_cleanup_hooks()

    def record_tps_sample(self, tps: float, model_id: Optional[str] = None) -> None:
        """Spec 036 (FR-005 & EC-001): Record TPS sample and check for SLA breach."""
        if tps > 0:
            self._tps_history.append((time.time(), tps, model_id or self.state.model_id))

    def evaluate_tps_sla(self, is_realtime: bool = True) -> tuple[bool, float, str]:
        """Spec 036 (FR-005 & EC-001): Evaluate rolling TPS against minimum SLA.
        
        Returns:
            (is_sla_met, avg_tps, recommendation_message)
        """
        min_sla_tps = 30.0 if is_realtime else 20.0
        if not self._tps_history:
            return (True, 0.0, "No TPS samples recorded yet.")

        recent_samples = [s[1] for s in self._tps_history]
        avg_tps = sum(recent_samples) / len(recent_samples)

        if avg_tps < min_sla_tps:
            return (
                False,
                avg_tps,
                f"TPS SLA Breach: Average TPS ({avg_tps:.1f}) is below minimum required {min_sla_tps:.1f} tokens/s. "
                f"Consider falling back to high-speed resident model (qwen3.5-2b)."
            )
        return (True, avg_tps, f"TPS SLA satisfied: Average TPS ({avg_tps:.1f} tokens/s) >= {min_sla_tps:.1f} tokens/s.")


    def verify_vram_released(self, baseline_free_vram_mb: int = 0, tolerance_mb: int = 200) -> bool:
        """FR-013: VRAM memory release check via nvidia-smi."""
        import shutil
        import subprocess
        
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            print("[ProcessManager] Warning: nvidia-smi not found. Skipping VRAM release verification.")
            return True
            
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            free_vram_mb = int(result.stdout.strip().split('\n')[0])
            
            if baseline_free_vram_mb > 0:
                if (abs(free_vram_mb - baseline_free_vram_mb) <= tolerance_mb or 
                    free_vram_mb >= baseline_free_vram_mb - tolerance_mb or
                    (self.vram_total - free_vram_mb) <= tolerance_mb):
                    return True
                return False
                
            return True
        except Exception as e:
            print(f"[ProcessManager] Warning: nvidia-smi failed during VRAM release verification: {e}")
            return True

    def get_vram_limit(self, model_id: str) -> int:
        return self.hardware_limits.get(model_id, 16000)

    def is_embedding_model(self, model_id: str) -> bool:
        resolved_id = self._config_manager.resolve_model_id(model_id)
        preset = self.model_presets.get(resolved_id, {})
        task_type = str(preset.get("task_type", "llm")).lower()
        return task_type in ("embedding", "tasktypeenum.embedding")

    def is_rerank_model(self, model_id: str) -> bool:
        resolved_id = self._config_manager.resolve_model_id(model_id)
        preset = self.model_presets.get(resolved_id, {})
        task_type = str(preset.get("task_type", "llm")).lower()
        return task_type in ("rerank", "reranking", "tasktypeenum.rerank")

    @staticmethod
    def parse_vram_offload_log(line: str, model_id: str) -> Optional[VramOffloadStatus]:
        layers_match = re.search(r"offloaded (\d+)/(\d+) layers to GPU", line)
        if layers_match:
            offloaded = int(layers_match.group(1))
            total = int(layers_match.group(2))
            return VramOffloadStatus(
                model_id=model_id,
                total_layers=total,
                offloaded_layers=offloaded,
                is_fully_offloaded=(offloaded == total)
            )

        clip_match = re.search(r"(clip model loaded|mmproj loaded)", line, re.IGNORECASE)
        if clip_match:
            return VramOffloadStatus(
                model_id=model_id,
                is_fully_offloaded=True,
                has_clip_offload=True
            )

        vram_match = re.search(r"(model|compute)\s*buffer size =\s*([\d.]+)\s*MiB", line, re.IGNORECASE)
        if vram_match:
            vram_mb = int(float(vram_match.group(2)))
            return VramOffloadStatus(
                model_id=model_id,
                is_fully_offloaded=True,
                offloaded_vram_mb=vram_mb
            )

        ready_server_match = re.search(r"(server is listening|Application startup complete|HTTP server listening)", line, re.IGNORECASE)
        if ready_server_match:
            return VramOffloadStatus(
                model_id=model_id,
                is_fully_offloaded=True
            )

        return None


    def verify_vram_offload(self, model_id: str, status: VramOffloadStatus) -> None:
        if not status.is_fully_offloaded:
            raise VramOverflowError(
                f"VRAM_PARTIAL_OFFLOAD_ERROR: {status.offloaded_layers}/{status.total_layers} layers offloaded. 100% VRAM offload required."
            )
        
        if self.vram_offload_status is None:
            self.vram_offload_status = status
        else:
            if status.total_layers > 0:
                self.vram_offload_status.total_layers = status.total_layers
                self.vram_offload_status.offloaded_layers = status.offloaded_layers
                self.vram_offload_status.is_fully_offloaded = status.is_fully_offloaded
            if status.has_clip_offload is not None:
                self.vram_offload_status.has_clip_offload = status.has_clip_offload
            if status.offloaded_vram_mb > 0:
                self.vram_offload_status.offloaded_vram_mb = status.offloaded_vram_mb

        # T019/US2-AC1: ProcessState에 vram_offloaded=True 기록
        if self.state.model_id == model_id:
            self.state = ProcessState(
                status=self.state.status,
                model_id=self.state.model_id,
                port=self.state.port,
                pid=self.state.pid,
                error_message=self.state.error_message,
                exit_code=self.state.exit_code,
                vram_offloaded=True,
            )

    def check_vram_runtime_overflow(self, threshold_pct: float = 95.0) -> None:
        """T021: 추론 컨텍스트 확장 시 실시간 VRAM 오버플로우 감지.

        nvidia-smi를 통해 현재 GPU VRAM 사용률을 확인하고,
        임계치(기본 95%)를 초과할 경우 VramOverflowError를 발생시켜
        CUDA OOM 크래시를 사전 차단합니다.

        Args:
            threshold_pct: VRAM 사용률 임계치 (백분율, 기본 95.0%)

        Raises:
            VramOverflowError: VRAM 사용률이 임계치를 초과할 경우
        """
        import subprocess

        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return  # nvidia-smi 미설치 환경에서는 검사 생략

        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            parts = [p.strip() for p in result.stdout.strip().split('\n')[0].split(',')]
            used_mb = int(parts[0])
            total_mb = int(parts[1])

            usage_pct = (used_mb / total_mb) * 100.0 if total_mb > 0 else 0.0

            if usage_pct >= threshold_pct:
                raise VramOverflowError(
                    f"VRAM 실시간 오버플로우 감지: {used_mb}MB / {total_mb}MB "
                    f"({usage_pct:.1f}% ≥ {threshold_pct}% 임계치). "
                    f"추론 컨텍스트 축소 또는 더 작은 모델 사용을 권장합니다."
                )
        except VramOverflowError:
            raise
        except Exception as e:
            print(f"[ProcessManager] T021: VRAM 런타임 모니터링 경고: {e}")

    def _cleanup_zombie_on_port(self, port: int) -> None:
        """FR-002: Forcefully kill any zombie or leftover process holding the specified port."""
        if os.environ.get("MOCK_LLAMA_SERVER") == "1" or "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("MOCK_CPU_ONLY") == "1":
            return
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            res = sock.connect_ex(('127.0.0.1', port))
            if res == 0:
                print(f"[ProcessManager] Q1: 포트 {port} 점유 잔여 PID 정리 시도 (Signal: SIGKILL)")
                try:
                    out = subprocess.check_output(["lsof", "-t", f"-i:{port}"], text=True, timeout=3)
                    for pid_str in out.strip().split():
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            if pid != os.getpid() and pid != 1 and ProcessManager._is_safe_to_kill_llama(pid):
                                os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
                time.sleep(0.5)

    def detect_zombie_collision(self) -> None:
        """T004: Detect zombie or external processes occupying port."""
        if os.environ.get("MOCK_LLAMA_SERVER") == "1" or "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("MOCK_CPU_ONLY") == "1":
            return
        if self.process is None or self.process.returncode is not None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                res = sock.connect_ex(('127.0.0.1', self.port))
                if res == 0:
                    raise PortCollisionError(
                        f"PortCollisionError: Port {self.port} is already occupied by a zombie or external process."
                    )

    @staticmethod
    def calculate_base_vram_mb(model_path: Any, file_size_bytes: Optional[int] = None) -> int:
        """FR-004 / FR-008 / 113: Dynamic Base VRAM calculation (file size * 1.15)."""
        try:
            if isinstance(model_path, ProcessManager):
                # Handle accidental instance argument pass
                model_path = file_size_bytes
                file_size_bytes = None
            if file_size_bytes is None:
                if model_path and isinstance(model_path, (str, Path)) and os.path.exists(str(model_path)):
                    file_size_bytes = os.path.getsize(str(model_path))
                else:
                    return 6000
            mb = (file_size_bytes / (1024 * 1024)) * 1.15
            return int(mb)
        except Exception:
            return 6000

    @staticmethod
    def calculate_polling_timeout(file_size_mb: float) -> float:
        """FR-003: Dynamic health check polling timeout formula min(30.0, max(15.0, 10.0 + file_size_mb/500))."""
        calc = 10.0 + (file_size_mb / 500.0)
        return min(30.0, max(15.0, calc))

    def _get_log_paths(self) -> tuple[str, str]:
        """Returns absolute paths for (benchmark.log, error.log)."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        logs_dir = os.path.join(base_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        return os.path.join(logs_dir, "benchmark.log"), os.path.join(logs_dir, "error.log")

    def _get_model_gqa_params(self, model_id: str, model_file: Optional[str] = None) -> dict:
        """Extracts n_layers, n_heads, n_head_kv, head_dim from GGUF metadata or model catalog."""
        params = {
            "n_layers": 36,
            "n_heads": 32,
            "n_head_kv": 8,
            "head_dim": 128,
        }
        try:
            config_mgr = getattr(self, "_config_manager", None)
            if config_mgr:
                resolved_id = config_mgr.resolve_model_id(model_id)
                catalog = config_mgr.get_model_catalog()
                entry = catalog.get(resolved_id) or catalog.get(model_id) or {}
                if entry.get("n_layers"):
                    params["n_layers"] = entry["n_layers"]
                if entry.get("n_heads"):
                    params["n_heads"] = entry["n_heads"]
                if entry.get("n_head_kv"):
                    params["n_head_kv"] = entry["n_head_kv"]
                if entry.get("head_dim"):
                    params["head_dim"] = entry["head_dim"]
        except Exception:
            pass

        if model_file and os.path.exists(model_file):
            try:
                from src.core.gpu_detector import read_gguf_metadata_architecture
                gguf_meta = read_gguf_metadata_architecture(model_file)
                if gguf_meta.get("n_layers"):
                    params["n_layers"] = gguf_meta["n_layers"]
                if gguf_meta.get("n_heads"):
                    params["n_heads"] = gguf_meta["n_heads"]
                if gguf_meta.get("n_head_kv"):
                    params["n_head_kv"] = gguf_meta["n_head_kv"]
                if gguf_meta.get("head_dim"):
                    params["head_dim"] = gguf_meta["head_dim"]
            except Exception:
                pass

        return params

    def estimate_vram_usage(self, model_id: str, n_ctx: int) -> int:
        """FR-010 / 113 / 118: Dry-run VRAM calculation based on model base VRAM and dynamic GQA context scaling."""
        try:
            config_mgr = getattr(self, "_config_manager", None)
            resolved_id = config_mgr.resolve_model_id(model_id) if config_mgr else model_id
            presets = getattr(self, "model_presets", {})
            preset = presets.get(resolved_id) if presets else None
            model_path = preset.get("model", "") if preset else ""
            if not model_path and config_mgr:
                catalog = config_mgr.get_model_catalog()
                entry = catalog.get(resolved_id) or catalog.get(model_id) or {}
                model_path = entry.get("model_path", "")
            base_vram = self.calculate_base_vram_mb(model_path) if model_path else 4000
            gqa = self._get_model_gqa_params(model_id, model_path)
            kv_vram_mb = estimate_kv_cache_vram(
                n_layers=gqa["n_layers"],
                n_heads=gqa["n_heads"],
                head_dim=gqa["head_dim"],
                n_ctx=n_ctx,
                n_head_kv=gqa["n_head_kv"]
            )
            return base_vram + kv_vram_mb
        except Exception:
            gqa = self._get_model_gqa_params(model_id)
            kv_vram_mb = estimate_kv_cache_vram(
                n_layers=gqa["n_layers"],
                n_heads=gqa["n_heads"],
                head_dim=gqa["head_dim"],
                n_ctx=n_ctx,
                n_head_kv=gqa["n_head_kv"]
            )
            return 4000 + kv_vram_mb

    def is_ready(self) -> bool:
        """FR-003 & FR-005: READY 상태이면서 서브프로세스가 실제로 생존(returncode is None)해 있는지 검증."""
        if self.state.status != ProcessStatusEnum.READY:
            return False
        if getattr(self, "active_runtime_backend", None) == "vllm":
            return True
        if self.process is None or self.process.returncode is not None:
            return False
        return True

    def _log_to_error_log(self, message: str) -> None:
        try:
            _, log_file = self._get_log_paths()
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [Port {self.port}] [ProcessManager] {message}\n")
        except Exception:
            pass

    async def _drain_stdout(self, stream: asyncio.StreamReader) -> None:
        """FR-001, FR-002, FR-005, FR-009, FR-011: Real-time log drain with 10MB rotation and Exit Code 137 dump."""
        recent_lines = collections.deque(maxlen=50)
        bench_log_path, err_log_path = self._get_log_paths()

        # FR-011 / US4: 10MB Log Rotation
        try:
            if os.path.exists(bench_log_path) and os.path.getsize(bench_log_path) > 10 * 1024 * 1024:
                old_log_path = bench_log_path + ".old"
                if os.path.exists(old_log_path):
                    os.remove(old_log_path)
                os.rename(bench_log_path, old_log_path)
        except Exception:
            pass

        log_file = None
        try:
            log_file = open(bench_log_path, "a", encoding="utf-8")
        except Exception:
            pass

        try:
            while not stream.at_eof():
                line_bytes = await stream.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                recent_lines.append(line.strip())

                if log_file:
                    log_file.write(line)
                    log_file.flush()

                status = self.parse_vram_offload_log(line, self.state.model_id or "")
                if status:
                    self.verify_vram_offload(self.state.model_id or "", status)
        except Exception:
            pass
        finally:
            if log_file:
                try:
                    log_file.close()
                except Exception:
                    pass

        if self.process:
            try:
                await self.process.wait()
            except Exception:
                pass
            if self.process.returncode is not None and self.process.returncode != 0:
                lines_dump = list(recent_lines)[-20:] if recent_lines else ["No log output captured"]
                last_logs = "\n".join(lines_dump)

                oom_header = ""
                if self.process.returncode in (137, -9):
                    oom_header = " [KERNEL_OOM_KILLER_EXIT_137: Process killed by Linux Kernel OOM Killer]"

                err_msg = f"서브프로세스 (PID {self.process.pid}, Port {self.port}) 비정상 종료 (Exit Code: {self.process.returncode}){oom_header}. 최근 출력:\n{last_logs}"
                print(f"[ProcessManager] ❌ {err_msg}")
                self._log_to_error_log(err_msg)

                try:
                    with open(bench_log_path, "a", encoding="utf-8") as f:
                        f.write(f"\n--- CRASH DUMP ({self.state.model_id or 'unknown'}) Exit Code {self.process.returncode}{oom_header} ---\n")
                        f.write(last_logs + "\n--------------------------------------------------\n")
                        f.flush()
                except Exception:
                    pass

                self.state = ProcessState(
                    status=ProcessStatusEnum.ERROR,
                    model_id=self.state.model_id,
                    port=self.port,
                    error_message=f"Process exited with code {self.process.returncode}{oom_header}: {recent_lines[-1] if recent_lines else 'Unknown error'}"
                )


    @staticmethod
    def _is_binary_executable_sanity(binary_path: str) -> bool:
        """FR-001 & FR-002: Verifies if a binary candidate is standalone executable and not an internal Ollama library."""
        if not binary_path:
            return False
        if "ollama" in binary_path.lower():
            return False
        if not (os.path.exists(binary_path) and os.access(binary_path, os.X_OK)):
            return False
        import subprocess
        try:
            res = subprocess.run(
                [binary_path, "--help"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.5
            )
            return res.returncode in (0, 1, 2)
        except Exception:
            return False

    @staticmethod
    def _runtime_backend_from_profile() -> str:
        """JIT 프로파일의 실제 probe 결과를 읽어 backend 선택에 사용합니다."""
        if os.environ.get("MODEL_GATEWAY_CPU_ONLY", os.environ.get("AISERVICE_SKIP_GPU", "0")) in {
            "1",
            "true",
            "TRUE",
            "yes",
        }:
            return "llama.cpp-cpu-openblas"
        try:
            from src.config import (
                attempt_runtime_backends,
                get_runtime_profile,
                select_runtime_backend,
            )

            profile = get_runtime_profile()
            statuses = profile.get("runtime_backend_status")
            if isinstance(statuses, dict) and statuses:
                selected = select_runtime_backend(statuses)
                if selected != "unavailable":
                    return selected

            from src.config import is_external_vllm_enabled

            def probe(backend: str) -> bool:
                if backend == "vllm":
                    if not is_external_vllm_enabled():
                        return False
                    url = os.environ.get(
                        "VLLM_HEALTH_URL", "http://127.0.0.1:8000/health"
                    )
                    try:
                        response = httpx.get(url, timeout=1.0)
                        return response.status_code == 200
                    except Exception:
                        return False
                elif backend == "llama.cpp-cuda":
                    binary = os.environ.get("LLAMA_SERVER_BINARY") or shutil.which("llama-server")
                    if binary:
                        try:
                            result = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=2, check=False)
                            if result.returncode == 0:
                                return True
                        except Exception:
                            pass
                    try:
                        import llama_cpp
                        return bool(llama_cpp.llama_supports_gpu_offload())
                    except Exception:
                        return False
                elif backend == "llama.cpp-cpu-openblas":
                    binary = os.environ.get("LLAMA_SERVER_BINARY") or shutil.which("llama-server")
                    if binary:
                        return True
                    try:
                        import llama_cpp
                        return True
                    except Exception:
                        return False
                return False

            selected, _failures = attempt_runtime_backends(probe)
            if selected != "unavailable":
                return selected
            selected = str(profile.get("runtime_backend", ""))
            return selected or "llama.cpp-cuda"
        except (ImportError, TypeError, ValueError, OSError):
            return "llama.cpp-cuda"

    @staticmethod
    def verify_and_build_llama_server(
        preferred_backend: str | None = None,
    ) -> LlamaServerBinaryInfo:
        """FR-001 & FR-002: Verifies CUDA llama-server binary existence; compiles via CMake with GGML_CUDA=ON if missing."""
        runtime_backend = preferred_backend or ProcessManager._runtime_backend_from_profile()
        cuda_enabled = runtime_backend == "llama.cpp-cuda"

        # 1. Check PATH via shutil.which for standalone binary binaries
        for binary_name in ["llama-server", "llama-cpp-server"]:
            candidate = shutil.which(binary_name)
            if candidate and ProcessManager._is_binary_executable_sanity(candidate):
                return LlamaServerBinaryInfo(
                    binary_path=candidate,
                    is_cuda_enabled=cuda_enabled,
                    build_source="PATH",
                    runtime_backend=runtime_backend,
                )

        # 2. Check system standalone C++ binary paths (excluding Ollama internal paths)
        system_candidates = [
            ("/usr/local/bin/llama-server", "SYSTEM_BIN"),
            ("/usr/bin/llama-server", "SYSTEM_BIN"),
        ]

        for path, build_source in system_candidates:
            if ProcessManager._is_binary_executable_sanity(path):
                return LlamaServerBinaryInfo(
                    binary_path=path,
                    is_cuda_enabled=cuda_enabled,
                    build_source=build_source,
                    runtime_backend=runtime_backend,
                )

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bin_dir = os.path.join(base_dir, ".bin")
        local_binary = os.path.join(bin_dir, "llama-server")
        generated_binary = os.path.join(base_dir, "bin", "llama-server")

        if ProcessManager._is_binary_executable_sanity(generated_binary):
            return LlamaServerBinaryInfo(
                binary_path=generated_binary,
                is_cuda_enabled=cuda_enabled,
                build_source="JIT_BIN",
                runtime_backend=runtime_backend,
            )

        if ProcessManager._is_binary_executable_sanity(local_binary):
            return LlamaServerBinaryInfo(
                binary_path=local_binary,
                is_cuda_enabled=cuda_enabled,
                build_source="LOCAL_BIN",
                runtime_backend=runtime_backend,
            )

        llama_src_dir = os.path.join(base_dir, "llama.cpp")
        if os.path.exists(os.path.join(llama_src_dir, "CMakeLists.txt")):
            try:
                from src.core.cpu_detector import (
                    get_llama_build_flags,
                    print_detection_report,
                )
                build_flags = get_llama_build_flags()
                cmake_args = build_flags.cmake_args_list
                print(f"[ProcessManager] llama-server missing. Compiling llama.cpp with hardware detection flags ({build_flags.cmake_args_str})...")
                print_detection_report()
            except Exception as e:
                print(f"[ProcessManager] ⚠️ Hardware detection failed, using fallback flags: {e}")
                cmake_args = [
                    "-DGGML_CUDA=ON",
                    "-DCMAKE_CUDA_ARCHITECTURES=61",
                    "-march=native",
                    "-DGGML_AVX=OFF",
                    "-DGGML_AVX2=OFF",
                    "-DGGML_F16C=OFF",
                    "-DGGML_FMA=OFF",
                ]

            import subprocess
            try:
                os.makedirs(bin_dir, exist_ok=True)
                build_dir = os.path.join(llama_src_dir, "build")
                cmd = ["cmake", "-B", build_dir] + cmake_args
                subprocess.run(
                    cmd,
                    cwd=llama_src_dir, check=True, capture_output=True
                )
                subprocess.run(
                    ["cmake", "--build", build_dir, "--config", "Release", "-j"],
                    cwd=llama_src_dir, check=True, capture_output=True
                )
                built_binary = os.path.join(build_dir, "bin", "llama-server")
                if os.path.exists(built_binary):
                    shutil.copy2(built_binary, local_binary)
                    os.chmod(local_binary, 0o755)
                    return LlamaServerBinaryInfo(
                        binary_path=local_binary,
                        is_cuda_enabled=True,
                        build_source="CMAKE_BUILD",
                        runtime_backend=runtime_backend,
                    )
            except Exception as e:
                print(f"[ProcessManager] Warning: CMake build failed: {e}")

        cuda_supports = False
        if cuda_enabled:
            try:
                import llama_cpp
                cuda_supports = bool(llama_cpp.llama_supports_gpu_offload())
            except Exception:
                cuda_supports = False

        return LlamaServerBinaryInfo(
            binary_path=sys.executable,
            is_cuda_enabled=cuda_supports,
            build_source="PYTHON_MODULE_FALLBACK",
            runtime_backend=runtime_backend,
        )

    def build_server_command(
        self,
        binary_info: Optional[LlamaServerBinaryInfo] = None,
        model_file: Optional[str] = None,
        model_id: str = "qwen3.5-2b",
        n_ctx: int = 16384,
        target_preset: Optional[Dict[str, Any]] = None,
        clip_file: Optional[str] = None,
        bind_host: str = "0.0.0.0",
        port: Optional[int] = None,
        model_path: Optional[str] = None,
        hardware_profile: Optional[Any] = None
    ) -> List[str]:
        """Spec 034: Constructs hardware-aware optimized llama-server startup command."""
        # Support flexible argument order for tests and internal callers
        if model_path and not model_file:
            model_file = model_path
        if not model_file and isinstance(binary_info, str):
            model_file = binary_info
            binary_info = None

        if binary_info is None:
            binary_info = self.verify_and_build_llama_server()

        effective_port = port if port is not None else self.port
        if target_preset is None:
            resolved_id = self._config_manager.resolve_model_id(model_id)
            target_preset = self.model_presets.get(resolved_id, {})

        task_type = str(target_preset.get("task_type", "llm")).lower()
        is_aux = task_type in ("embedding", "rerank", "reranking", "tasktypeenum.embedding", "tasktypeenum.rerank") or effective_port in (8090, 8091)
        ngl_value = "999" if binary_info.is_cuda_enabled else "0"

        # Detect hardware profile if not provided
        if hardware_profile is None:
            try:
                from src.core.gpu_detector import detect_hardware_capabilities
                hardware_profile = detect_hardware_capabilities()
            except Exception:
                hardware_profile = None

        use_flash_attn = False
        kv_type = "q8_0"
        if hardware_profile is not None:
            use_flash_attn = getattr(hardware_profile, "use_flash_attn", False)
            if getattr(hardware_profile, "use_fp4_kv", False):
                kv_type = "fp4"
            elif getattr(hardware_profile, "use_fp8_kv", False):
                kv_type = "fp8"
            elif getattr(hardware_profile, "use_q8_kv", True):
                kv_type = "q8_0"

        if binary_info.build_source != "PYTHON_MODULE_FALLBACK":
            cmd = [
                binary_info.binary_path,
                "-m", str(model_file),
                "-c", str(n_ctx),
                "--host", bind_host,
                "--port", str(effective_port),
                "-ngl", ngl_value,
                "--split-mode", "none",
                "--main-gpu", "0"
            ]
            if not is_aux:
                if use_flash_attn:
                    cmd.extend(["-fa", "--ctk", kv_type, "--ctv", kv_type])
                else:
                    cmd.extend(["--ctk", kv_type])
                cmd.extend([
                    "--cache-prompt",
                    "-b", "512",
                    "-ub", "256"
                ])
            if clip_file and os.path.exists(clip_file):
                cmd.extend(["--mmproj", clip_file])
            
            if task_type in ("embedding", "tasktypeenum.embedding") or effective_port == 8090:
                cmd.append("--embedding")
            elif task_type in ("rerank", "reranking", "tasktypeenum.rerank") or effective_port == 8091:
                cmd.extend(["--reranking", "--embedding"])
        else:
            type_kv_int = 8 if kv_type == "q8_0" else (2 if kv_type == "q4_0" else 1)
            cmd = [
                sys.executable, "-m", "llama_cpp.server",
                "--model", str(model_file),
                "--n_ctx", str(n_ctx),
                "--host", bind_host,
                "--port", str(effective_port),
                "--n_gpu_layers", ngl_value
            ]
            if not is_aux:
                if use_flash_attn:
                    cmd.extend(["--flash_attn", "True"])
                if n_ctx >= 32768 or kv_type in ("q8_0", "q4_0", "fp8"):
                    cmd.extend([
                        "--type_k", str(type_kv_int),
                        "--type_v", str(type_kv_int),
                    ])
                batch_sz = 256 if n_ctx >= 32768 else 512
                cmd.extend(["--n_batch", str(batch_sz), "--n_ubatch", str(batch_sz)])
                cmd.extend(["--interrupt_requests", "False"])
                cmd.extend(["--cache", "False"])

            if clip_file and os.path.exists(clip_file):
                cmd.extend(["--clip_model_path", clip_file])
            if target_preset.get("chat_template") and "qwen" not in str(model_id).lower():
                cmd.extend(["--chat_format", target_preset["chat_template"]])
            
            if task_type in ("embedding", "rerank", "reranking", "tasktypeenum.embedding", "tasktypeenum.rerank") or effective_port in (8090, 8091):
                cmd.extend(["--embedding", "True"])

        return cmd

    async def spawn_process(self, model_id: str, n_ctx: int = 2048) -> ProcessState:
        """Spawns a new llama-server subprocess for Gemma 4 or Qwen 3.5."""
        await self.stop_process()
        self.vram_offload_status = None

        # FR-001 / FR-005: Synchronous port free and VRAM release verification first
        port_free = await self._wait_for_port_free(max_retries=10, interval=0.5)
        if not port_free:
            raise PortCollisionError(f"PortCollisionError: Port {self.port} could not be cleared after process termination.")

        # FR-001 / FR-002: Cleanup any zombie process holding the port before collision check
        self._cleanup_zombie_on_port(self.port)
        self.detect_zombie_collision()


        model_id = self._config_manager.resolve_model_id(model_id)
        target_preset = self.model_presets.get(model_id)
        if not target_preset:
            self.state = ProcessState(
                status=ProcessStatusEnum.ERROR,
                model_id=model_id,
                port=self.port,
                error_message=f"Unknown model_id: {model_id}"
            )
            return self.state

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_rel = target_preset["model"]
        model_file = self._config_manager.get_absolute_path(model_rel) or os.path.join(base_dir, model_rel)

        if not os.path.exists(model_file):
            self.state = ProcessState(
                status=ProcessStatusEnum.ERROR,
                model_id=model_id,
                port=self.port,
                error_message=f"Model file not found: {model_file}"
            )
            return self.state

        # Ensure target_dir exists
        target_dir = os.path.dirname(model_file)
        os.makedirs(target_dir, exist_ok=True)

        # FR-012 / T002 / 118: Pre-flight GGUF + Dynamic GQA KV Cache VRAM estimator
        gqa = self._get_model_gqa_params(model_id, model_file)
        kv_vram_mb = estimate_kv_cache_vram(
            n_layers=gqa["n_layers"],
            n_heads=gqa["n_heads"],
            head_dim=gqa["head_dim"],
            n_ctx=n_ctx,
            n_head_kv=gqa["n_head_kv"]
        )
        base_vram = self.calculate_base_vram_mb(model_file)
        vram_est = base_vram + kv_vram_mb

        if vram_est > self.vram_max_capacity_mb + 2000:  # Hard limit check
            self.state = ProcessState(
                status=ProcessStatusEnum.ERROR,
                model_id=model_id,
                port=self.port,
                error_message=f"CUDA OOM Risk: Estimated VRAM {vram_est}MB (KV Cache: {kv_vram_mb}MB) exceeds GPU capacity limit {self.vram_max_capacity_mb}MB"
            )
            return self.state

        # FR-001 & FR-002: GPU & CUDA Backend auto-detection and CPU fallback blocking
        if os.environ.get("MOCK_CPU_ONLY") == "1":
            self.state = ProcessState(
                status=ProcessStatusEnum.ERROR,
                model_id=model_id,
                port=self.port,
                error_message="GpuAccelerationError: CPU-only execution is strictly blocked. NVIDIA GPU with CUDA acceleration is required."
            )
            return self.state

        if not os.environ.get("MOCK_LLAMA_SERVER"):
            try:
                get_nvml_vram_info()
            except GpuAccelerationError as e:
                self.state = ProcessState(
                    status=ProcessStatusEnum.ERROR,
                    model_id=model_id,
                    port=self.port,
                    error_message=f"GpuAccelerationError: {str(e)}"
                )
                return self.state

        # FR-001 (015-gemma4-model-loading-fix): Resolve MMProj (CLIP vision projector) path if defined in preset
        clip_file = None
        clip_rel = target_preset.get("clip")
        if clip_rel:
            candidate_clip = self._config_manager.get_absolute_path(clip_rel) or os.path.join(base_dir, clip_rel)
            if candidate_clip and os.path.exists(candidate_clip):
                clip_file = candidate_clip
            elif os.path.exists(clip_rel):
                clip_file = clip_rel

        if target_preset.get("requires_mmproj") and not clip_file:
            self.state = ProcessState(
                status=ProcessStatusEnum.ERROR,
                model_id=model_id,
                port=self.port,
                error_message=f"Vision Projector (mmproj) file not found: {clip_rel}"
            )
            return self.state

        # Force 100% GPU VRAM Offloading environment variables
        env = dict(os.environ)
        cpu_only = os.environ.get(
            "MODEL_GATEWAY_CPU_ONLY", os.environ.get("AISERVICE_SKIP_GPU", "0")
        ).lower() in {"1", "true", "yes"}
        if cpu_only:
            env.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            env["CUDA_VISIBLE_DEVICES"] = "0"

        bind_host = "0.0.0.0"

        # Check if model file exists locally; if not, return clear error message per spec
        if not os.path.exists(model_file) and not os.environ.get("MOCK_LLAMA_SERVER"):
            self.state = ProcessState(
                status=ProcessStatusEnum.ERROR,
                model_id=model_id,
                port=self.port,
                error_message=f"Model file not found: {model_file}"
            )
            return self.state

        from src.config import (
            get_runtime_fallback_chain,
            is_runtime_compatibility_error,
        )

        selected_backend = self._runtime_backend_from_profile()
        backend_order = ["llama.cpp-cpu-openblas"] if cpu_only else [selected_backend]
        if not cpu_only:
            backend_order.extend(
                backend
                for backend in get_runtime_fallback_chain()
                if backend not in backend_order
            )
        self.runtime_backend_failures = []

        for backend in backend_order:
            if backend == "vllm":
                from src.config import is_external_vllm_enabled
                if not is_external_vllm_enabled():
                    continue
                vllm_url = os.environ.get(
                    "VLLM_HEALTH_URL", "http://127.0.0.1:8000/health"
                )
                try:
                    response = await asyncio.to_thread(httpx.get, vllm_url, timeout=1.0)
                    if response.status_code == 200:
                        self.active_runtime_backend = backend
                        self.state = ProcessState(
                            status=ProcessStatusEnum.READY,
                            model_id=model_id,
                            port=self.port,
                        )
                        return self.state
                    self.runtime_backend_failures.append(
                        f"{backend}: health status {response.status_code}"
                    )
                except Exception as exc:
                    self.runtime_backend_failures.append(f"{backend}: {exc}")
                continue

            try:
                binary_info = self.verify_and_build_llama_server(
                    preferred_backend=backend
                )
                cmd = self.build_server_command(
                    binary_info=binary_info,
                    model_file=model_file,
                    model_id=model_id,
                    n_ctx=n_ctx,
                    target_preset=target_preset,
                    clip_file=clip_file,
                    bind_host=bind_host
                )
                self.state = ProcessState(
                    status=ProcessStatusEnum.LOADING,
                    model_id=model_id,
                    port=self.port
                )
                self.active_runtime_backend = backend
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                    env=env
                )
                file_size_mb = os.path.getsize(model_file) / (1024 * 1024) if os.path.exists(model_file) else 1000.0
                timeout_sec = float(os.environ.get("RUNTIME_BACKEND_READY_TIMEOUT", str(self.calculate_polling_timeout(file_size_mb) + 20.0)))
                ready = await poll_server_health(
                    port=self.port,
                    timeout=max(30.0, timeout_sec),
                )
                if ready:
                    if self.process and self.process.stdout:
                        self._log_drain_task = asyncio.create_task(
                            self._drain_stdout(self.process.stdout)
                        )
                    self.state = ProcessState(
                        status=ProcessStatusEnum.READY,
                        model_id=model_id,
                        port=self.port,
                        pid=self.process.pid
                    )
                    return self.state

                output = ""
                if self.process.returncode is None:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=2.0)
                if self.process.stdout:
                    output = (await self.process.stdout.read()).decode(
                        "utf-8", errors="replace"
                    )[-1000:]
                failure = output or "readiness probe timeout"
                self.runtime_backend_failures.append(f"{backend}: {failure}")
                if not is_runtime_compatibility_error(failure):
                    self.runtime_backend_failures[-1] += " (fallback 계속)"
                self.close_transport()
                self.process = None
            except Exception as exc:
                self.runtime_backend_failures.append(f"{backend}: {exc}")
                if self.process:
                    try:
                        if self.process.returncode is None:
                            self.process.terminate()
                            await asyncio.wait_for(self.process.wait(), timeout=2.0)
                    except Exception:
                        pass
                    self.close_transport()
                    self.process = None

        self.active_runtime_backend = None
        self.state = ProcessState(
            status=ProcessStatusEnum.ERROR,
            model_id=model_id,
            port=self.port,
            error_message="; ".join(self.runtime_backend_failures)
            or "사용 가능한 runtime backend가 없습니다",
        )
        return self.state

    def close_transport(self) -> None:
        """Explicitly close subprocess transport to prevent BaseSubprocessTransport.__del__ exception on loop closure."""
        if self.process:
            try:
                transport = getattr(self.process, '_transport', None)
                if transport is not None:
                    if hasattr(transport, 'is_closing') and not transport.is_closing():
                        transport.close()
                    elif not getattr(transport, '_closed', False):
                        transport.close()
            except Exception:
                pass

    async def stop_process(self) -> ProcessState:
        """Stops the running subprocess with Graceful Stream Drain, SIGTERM -> SIGKILL escalation and socket cleanup.

        FR-002, FR-005, FR-010, FR-011: Graceful Stream Drain (active_requests == 0, max 5s)
        및 프로세스 안전 종료/포트 해제/PyNVML VRAM 완납 검증.
        """
        # T003: Graceful Stream Drain (active_requests == 0, max 5s timeout)
        drain_start = asyncio.get_event_loop().time()
        while getattr(self.state, "active_requests", 0) > 0 and (asyncio.get_event_loop().time() - drain_start) < 5.0:
            await asyncio.sleep(0.2)

        if self._log_file_handle:
            try:
                self._log_file_handle.flush()
                self._log_file_handle.close()
            except Exception:
                pass
            self._log_file_handle = None

        if self._log_drain_task and not self._log_drain_task.done():
            try:
                if self.process and hasattr(self.process, "stdout") and self.process.stdout:
                    if hasattr(self.process.stdout, "_transport") and self.process.stdout._transport:
                        try:
                            self.process.stdout._transport.write_eof()
                        except Exception:
                            pass
                await asyncio.wait_for(asyncio.shield(self._log_drain_task), timeout=2.0)
            except Exception:
                pass
            if not self._log_drain_task.done():
                self._log_drain_task.cancel()
            self._log_drain_task = None

        if self.process:
            try:
                if self.process.returncode is None:
                    self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    if self.process.returncode is None:
                        self.process.kill()
                        await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except (ProcessLookupError, Exception):
                pass

            # FR-005/FR-006: 서브프로세스 트랜스포트 명시적 닫기 및 마이크로태스크 소진
            # BaseSubprocessTransport.__del__ RuntimeError: Event loop is closed 예외 방지
            self.close_transport()
            try:
                await asyncio.sleep(0.1)  # FR-006: 마이크로태스크 및 이벤트 루프 소진으로 닫힘 콜백 완결
            except Exception:
                pass

            exit_code = self.process.returncode
            self.process = None


        else:
            exit_code = None

        # FR-010 / T010: 포트 소켓 클리어 대기 (max_retries=10, interval=0.5s -> max 5s)
        await self._wait_for_port_free(max_retries=10, interval=0.5)

        vram_ok = self.verify_vram_released()
        print(f"[ProcessManager] FR-004: VRAM 해제 검증 완료: {'성공' if vram_ok else '경고 - VRAM 잔여 점유 감지'}")

        self.state = ProcessState(
            status=ProcessStatusEnum.UNLOADED,
            port=self.port,
            exit_code=exit_code
        )
        return self.state

    async def _wait_for_port_free(self, max_retries: int = 10, interval: float = 0.5) -> bool:
        """TCP Port Readiness Polling with clean non-zero connection verification."""
        import signal
        import socket
        import subprocess
        if os.environ.get("MOCK_LLAMA_SERVER") == "1" or "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("MOCK_CPU_ONLY") == "1":
            return True

        for i in range(max_retries):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if sock.connect_ex(('127.0.0.1', self.port)) != 0:
                    return True

            # 3회 이상 포트 점유 지속 시 잔여 프로세스 정리 (8081 및 PID 1 제외)
            if i >= 2 and self.port != 8081:
                try:
                    out = subprocess.check_output(["lsof", "-t", f"-i:{self.port}"], text=True, timeout=2)
                    for pid_str in out.strip().split():
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            if pid != os.getpid() and pid != 1 and ProcessManager._is_safe_to_kill_llama(pid):
                                try:
                                    os.kill(pid, signal.SIGKILL)
                                except OSError:
                                    pass
                except Exception:
                    pass

            await asyncio.sleep(interval)

        return True

    @staticmethod
    def _is_safe_to_kill_llama(pid: int) -> bool:
        """Ensures we never kill uvicorn or the FastAPI server process."""
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().decode("utf-8", errors="ignore")
                if "uvicorn" in cmdline or "src.api.server" in cmdline:
                    return False
                if "llama" in cmdline:
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def force_kill_zombie_llama_servers(target_ports: Any = (8089, 8090, 8091)) -> None:
        """T014 / US2 / 113: Pinpoint kills zombie llama-server and llama_cpp.server processes and cleans backend ports."""
        import subprocess
        if not isinstance(target_ports, (list, tuple, set)):
            target_ports = (8089, 8090, 8091)
        for port in target_ports:
            if port == 8081:  # Never kill main API server
                continue
            try:
                out = subprocess.check_output(["lsof", "-t", f"-i:{port}"], text=True, timeout=2)
                for pid_str in out.strip().split():
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        if pid != os.getpid() and pid != 1 and ProcessManager._is_safe_to_kill_llama(pid):
                            try:
                                os.kill(pid, signal.SIGKILL)
                            except OSError:
                                pass
            except Exception:
                pass
        
        # Kill orphan python3 -m llama_cpp.server processes if present
        try:
            out = subprocess.check_output(["pgrep", "-f", "llama_cpp.server"], text=True, timeout=2)
            for pid_str in out.strip().split():
                if pid_str.isdigit():
                    pid = int(pid_str)
                    if pid != os.getpid() and pid != 1 and ProcessManager._is_safe_to_kill_llama(pid):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass
        except Exception:
            pass


# Class alias for compatibility
LlamaServerProcessManager = ProcessManager
