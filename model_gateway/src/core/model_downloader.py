"""
HuggingFace Hub GGUF & mmproj CLIP 자동 다운로더 모듈 (FR-001, FR-002, FR-003).

지원 모델:
  - Qwen 3.5 (2B, 4B, 9B)
  - Qwen 3.6 (27B, 35B-A3B MoE)
  - Gemma 4 (E2B, E4B, 12B) with mmproj CLIP
  - Gemma 4 Text-Only (2B, 4B, 12B) without mmproj
  - Gemma 4 26B A4B MoE without mmproj

기능:
  - 로컬 파일 미존재 탐지 및 HuggingFace Hub 자동 다운로드
  - 이어받기(Resume) 및 진행률 콘솔 출력
  - 다운로드 상태 추적 (ModelDownloadTask Pydantic v2 모델)
"""

import os
import shutil
import time
from enum import Enum
from typing import Optional, Dict, List, Callable
from pydantic import BaseModel, ConfigDict, Field
from src.core.config_manager import ConfigManager


# ---------------------------------------------------------------------------
# Pydantic v2 데이터 모델 정의
# ---------------------------------------------------------------------------

class DownloadStatusEnum(str, Enum):
    """다운로드 상태 열거형."""
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class VRAMPrecheckResult(BaseModel):
    """VRAM 사전 검증 결과 엔티티."""
    model_config = ConfigDict(frozen=False)

    model_id: str = Field(..., description="모델 식별자")
    file_size_bytes: int = Field(default=0, description="GGUF 가중치 용량 (바이트)")
    estimated_vram_mb: float = Field(default=0.0, description="추정 VRAM 요구량 (MB)")
    available_vram_mb: float = Field(default=0.0, description="물리 GPU VRAM 용량 (MB)")
    kv_cache_vram_mb: float = Field(default=0.0, description="추정 KV Cache VRAM 용량 (MB)")
    is_feasible: bool = Field(default=True, description="VRAM 수용 가능 여부")
    status_code: str = Field(default="PASS", description="상태 코드 (PASS, SKIP_OOM_RISK, BYPASS_WARNING)")
    message: str = Field(default="", description="사용자 안내 메시지")


class ModelDownloadTask(BaseModel):
    """단일 모델 다운로드 작업 상태 추적 엔티티."""

    model_config = ConfigDict(frozen=False)

    model_id: str = Field(..., description="모델 식별자 (예: 'qwen3.5-2b')")
    repo_id: str = Field(..., description="HuggingFace Repository ID")
    filename: str = Field(..., description="GGUF 가중치 파일명")
    clip_filename: Optional[str] = Field(default=None, description="CLIP mmproj 파일명 (Gemma 4 전용)")
    target_dir: str = Field(..., description="로컬 저장 디렉토리 (예: 'models/qwen3.5-2b/')")
    status: DownloadStatusEnum = Field(default=DownloadStatusEnum.PENDING, description="다운로드 상태")
    download_progress_pct: float = Field(default=0.0, description="진행률 (0.0 ~ 100.0)")
    error_message: Optional[str] = Field(default=None, description="에러 메시지")


# Backward compatibility alias for tests
MODEL_DOWNLOAD_CATALOG: Dict[str, Dict] = ConfigManager().get_model_catalog()


# ---------------------------------------------------------------------------
# HuggingFace Hub 다운로드 엔진 (FR-001, FR-002, FR-003)
# ---------------------------------------------------------------------------

class ModelDownloader:

    """HuggingFace Hub 기반 GGUF 및 mmproj CLIP 자동 다운로더."""

    def __init__(self, base_dir: Optional[str] = None, config_manager: Optional[ConfigManager] = None):
        if base_dir is None:
            self.base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
        else:
            self.base_dir = base_dir

        self._tasks: Dict[str, ModelDownloadTask] = {}
        self.config_manager = config_manager or ConfigManager()

    @property
    def catalog(self) -> Dict[str, Dict]:
        """FR-001: ConfigManager 단일 진실 소스(Single Source of Truth)에서 다운로드 모델 카탈로그 반환."""
        ext_catalog = self.config_manager.get_model_catalog()
        res = {}
        for model_id, entry in ext_catalog.items():
            res[model_id] = {
                "repo_id": entry.get("repo_id", ""),
                "filename": entry.get("filename", ""),
                "clip_filename": entry.get("clip_filename"),
                "target_dir": entry.get("target_dir", f"models/{model_id}"),
                "size_gb": entry.get("size_gb", 0.0),
                "vram_est_mb": entry.get("vram_est_mb", 6000),
                "exact_bytes": entry.get("exact_bytes", 0),
            }
        return res


    def get_task(self, model_id: str) -> Optional[ModelDownloadTask]:
        """특정 모델의 다운로드 상태 조회."""
        return self._tasks.get(model_id)

    def get_all_tasks(self) -> Dict[str, ModelDownloadTask]:
        """전체 다운로드 상태 맵 반환."""
        return dict(self._tasks)

    def reconcile_catalog_metadata(self, model_id: str) -> bool:
        """FR-012: Measures actual local file size (bytes/GB) and updates model_catalog.json atomically."""
        model_id = self.config_manager.resolve_model_id(model_id)
        catalog_entry = self.catalog.get(model_id)
        if not catalog_entry:
            return False

        rel_path = catalog_entry.get("model_path")
        if not rel_path:
            return False

        abs_path = os.path.join(self.base_dir, rel_path)
        if not os.path.isfile(abs_path):
            return False

        actual_bytes = os.path.getsize(abs_path)
        actual_gb = round(actual_bytes / (1024 ** 3), 2)

        needs_update = False
        if catalog_entry.get("exact_bytes") != actual_bytes or catalog_entry.get("size_gb") != actual_gb:
            catalog_entry["exact_bytes"] = actual_bytes
            catalog_entry["size_gb"] = actual_gb
            needs_update = True

        if needs_update:
            try:
                catalog_file = os.path.join(self.base_dir, "config", "model_catalog.json")
                if os.path.exists(catalog_file):
                    with open(catalog_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if model_id in data:
                        data[model_id]["exact_bytes"] = actual_bytes
                        data[model_id]["size_gb"] = actual_gb
                        tmp_file = catalog_file + ".tmp"
                        with open(tmp_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4)
                        os.replace(tmp_file, catalog_file)
                        print(f"[ModelDownloader] 📝 FR-012: model_catalog.json 메타데이터 자율 동기화 완료: [{model_id}] {actual_bytes} bytes ({actual_gb} GB)")
                        return True
            except Exception as e:
                print(f"[ModelDownloader] ⚠️ FR-012 metadata sync failed: {e}", file=sys.stderr)
        return False

    def is_model_available(self, model_id: str) -> bool:
        """로컬에 해당 모델의 GGUF 가중치 및 MMProj CLIP 프로젝터 파일이 모두 존재하는지 확인."""
        model_id = self.config_manager.resolve_model_id(model_id)
        catalog_entry = self.catalog.get(model_id)
        if not catalog_entry:
            return False

        dirs_to_check = [catalog_entry["target_dir"]]
        if "e2b" in model_id:
            dirs_to_check.append("models/gemma4-2b")
        elif "e4b" in model_id:
            dirs_to_check.append("models/gemma4-4b")

        for rel_dir in dirs_to_check:
            abs_dir = os.path.join(self.base_dir, rel_dir)
            if not os.path.isdir(abs_dir):
                continue

            target_filename = catalog_entry.get("filename")
            has_main = False
            if target_filename:
                exact_main = os.path.join(abs_dir, target_filename)
                has_main = os.path.isfile(exact_main)
            if not has_main:
                has_main = any(f.endswith(".gguf") and "mmproj" not in f for f in os.listdir(abs_dir))

            if not has_main:
                continue

            clip_name = catalog_entry.get("clip_filename")
            has_clip = True
            if clip_name:
                exact_clip = os.path.join(abs_dir, clip_name)
                has_clip = os.path.isfile(exact_clip)
                if not has_clip:
                    has_clip = any(f.endswith(".gguf") and "mmproj" in f for f in os.listdir(abs_dir))
            if not has_clip:
                continue

            # FR-012: Trigger metadata reconciliation on Smart Skip detection
            self.reconcile_catalog_metadata(model_id)
            return True
        return False

    def get_model_path(self, model_id: str) -> Optional[str]:
        """모델의 로컬 GGUF 파일 절대 경로 반환. 미존재 시 None."""
        model_id = self.config_manager.resolve_model_id(model_id)
        catalog_entry = self.catalog.get(model_id)
        if not catalog_entry:
            return None

        dirs_to_check = [catalog_entry["target_dir"]]
        if "e2b" in model_id:
            dirs_to_check.append("models/gemma4-2b")
        elif "e4b" in model_id:
            dirs_to_check.append("models/gemma4-4b")

        for rel_dir in dirs_to_check:
            abs_dir = os.path.join(self.base_dir, rel_dir)
            if not os.path.isdir(abs_dir):
                continue
            exact_main = os.path.join(abs_dir, catalog_entry["filename"])
            if os.path.isfile(exact_main):
                return exact_main
            for f in os.listdir(abs_dir):
                if f.endswith(".gguf") and "mmproj" not in f:
                    return os.path.join(abs_dir, f)

        return None

    def check_vram_feasibility(
        self,
        model_id: str,
        n_ctx: int = 4096,
        ignore_vram_check: bool = False
    ) -> VRAMPrecheckResult:
        """FR-001, FR-002, FR-005: 대상 모델의 VRAM 요구량을 사전 산출하여 physical GPU VRAM 수용 여부를 판정합니다."""
        model_id = self.config_manager.resolve_model_id(model_id)
        catalog_entry = self.catalog.get(model_id, {})

        # 1. Determine file size bytes
        file_size_bytes = 0
        local_path = self.get_model_path(model_id)
        if local_path and os.path.isfile(local_path):
            file_size_bytes = os.path.getsize(local_path)
        else:
            file_size_bytes = catalog_entry.get("exact_bytes", 0)
            if not file_size_bytes:
                size_gb = catalog_entry.get("size_gb", 0)
                if size_gb:
                    file_size_bytes = int(size_gb * 1024 * 1024 * 1024)
                else:
                    vram_est = catalog_entry.get("vram_est_mb", 6000)
                    file_size_bytes = int((vram_est / 1.15) * 1024 * 1024)

        # 2. Calculate Base VRAM (file size * 1.15)
        base_vram_mb = (file_size_bytes / (1024 * 1024)) * 1.15 if file_size_bytes > 0 else 6000.0

        # 3. Calculate KV Cache VRAM
        try:
            from src.core.gpu_detector import estimate_kv_cache_vram
            kv_cache_vram_mb = float(estimate_kv_cache_vram(n_ctx=n_ctx))
        except Exception:
            kv_cache_vram_mb = 1152.0

        estimated_vram_mb = base_vram_mb + kv_cache_vram_mb

        # 4. Determine GPU physical VRAM capacity
        try:
            from src.core.gpu_detector import get_nvml_vram_info
            gpu_info = get_nvml_vram_info()
            available_vram_mb = float(gpu_info.total_vram_mb) if gpu_info.total_vram_mb > 0 else 11264.0
        except Exception:
            available_vram_mb = 11264.0

        # 5. Evaluate Feasibility
        if ignore_vram_check:
            return VRAMPrecheckResult(
                model_id=model_id,
                file_size_bytes=file_size_bytes,
                estimated_vram_mb=estimated_vram_mb,
                available_vram_mb=available_vram_mb,
                kv_cache_vram_mb=kv_cache_vram_mb,
                is_feasible=True,
                status_code="BYPASS_WARNING",
                message=f"[BYPASS VRAM Check] --ignore-vram-check 활성화: 추정 VRAM({int(estimated_vram_mb)}MB)이 VRAM({int(available_vram_mb)}MB)을 초과하나 실행 강제 부여됨"
            )

        if estimated_vram_mb > available_vram_mb:
            return VRAMPrecheckResult(
                model_id=model_id,
                file_size_bytes=file_size_bytes,
                estimated_vram_mb=estimated_vram_mb,
                available_vram_mb=available_vram_mb,
                kv_cache_vram_mb=kv_cache_vram_mb,
                is_feasible=False,
                status_code="SKIP_OOM_RISK",
                message=f"예상 VRAM 사용량({int(estimated_vram_mb)}MB)이 물리 GPU VRAM({int(available_vram_mb)}MB)을 초과하여 사전 스킵"
            )

        return VRAMPrecheckResult(
            model_id=model_id,
            file_size_bytes=file_size_bytes,
            estimated_vram_mb=estimated_vram_mb,
            available_vram_mb=available_vram_mb,
            kv_cache_vram_mb=kv_cache_vram_mb,
            is_feasible=True,
            status_code="PASS",
            message=f"VRAM 사전 검증 통과 ({int(estimated_vram_mb)}MB / {int(available_vram_mb)}MB)"
        )

    def download_model(
        self,
        model_id: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        force: bool = False,
        ignore_vram_check: bool = False,
    ) -> ModelDownloadTask:
        """단일 모델의 GGUF 가중치(및 CLIP mmproj)를 HuggingFace Hub에서 다운로드."""
        model_id = self.config_manager.resolve_model_id(model_id)
        catalog_entry = self.catalog.get(model_id)
        if not catalog_entry:
            task = ModelDownloadTask(
                model_id=model_id,
                repo_id="unknown",
                filename="unknown",
                target_dir="unknown",
                status=DownloadStatusEnum.FAILED,
                error_message=f"Unknown model_id: {model_id}",
            )
            self._tasks[model_id] = task
            return task

        task = ModelDownloadTask(
            model_id=model_id,
            repo_id=catalog_entry["repo_id"],
            filename=catalog_entry["filename"],
            clip_filename=catalog_entry.get("clip_filename"),
            target_dir=catalog_entry["target_dir"],
            status=DownloadStatusEnum.PENDING,
        )
        self._tasks[model_id] = task

        target_dir_abs = os.path.join(self.base_dir, catalog_entry["target_dir"])
        target_file = os.path.join(target_dir_abs, catalog_entry["filename"])
        clip_path = os.path.join(target_dir_abs, catalog_entry["clip_filename"]) if catalog_entry.get("clip_filename") else None

        main_exists = os.path.isfile(target_file)
        clip_exists = not clip_path or os.path.isfile(clip_path)

        if main_exists and clip_exists and not force:
            task.status = DownloadStatusEnum.SKIPPED
            task.download_progress_pct = 100.0
            print(f"[ModelDownloader] {model_id}: 이미 존재함 → {target_file}")
            if progress_callback:
                progress_callback(model_id, 100.0)
            return task

        # FR-001 / FR-002: Pre-download VRAM feasibility check
        feasibility = self.check_vram_feasibility(model_id, ignore_vram_check=ignore_vram_check)
        if not feasibility.is_feasible:
            task.status = DownloadStatusEnum.SKIPPED
            task.error_message = f"[SKIP VRAM OOM Risk] {feasibility.message}"
            print(f"[ModelDownloader] {model_id}: ⚠️ [SKIP VRAM OOM Risk] 예상 VRAM 사용량({int(feasibility.estimated_vram_mb)}MB)이 물리 GPU VRAM({int(feasibility.available_vram_mb)}MB)을 초과하므로 다운로드를 사전 스킵합니다.")
            return task


        os.makedirs(target_dir_abs, exist_ok=True)

        task.status = DownloadStatusEnum.DOWNLOADING
        print(f"[ModelDownloader] {model_id}: 다운로드 시작 → {catalog_entry['repo_id']}/{catalog_entry['filename']}")

        try:
            from huggingface_hub import hf_hub_download

            hf_token = os.environ.get("HF_TOKEN")
            t_start = time.time()
            downloaded_path = hf_hub_download(
                repo_id=catalog_entry["repo_id"],
                filename=catalog_entry["filename"],
                local_dir=target_dir_abs,
                token=hf_token,
                resume_download=True,
            )
            t_elapsed = max(0.001, time.time() - t_start)
            file_bytes = os.path.getsize(downloaded_path) if os.path.exists(downloaded_path) else 0
            size_mb = round(file_bytes / (1024 * 1024), 2)
            speed_mbps = round(size_mb / t_elapsed, 2)

            task.download_progress_pct = 80.0 if catalog_entry.get("clip_filename") else 100.0
            print(f"[ModelDownloader] {model_id}: GGUF 가중치 다운로드 완료 ({size_mb} MB, 평균 {speed_mbps} MB/s) → {downloaded_path}")
            if progress_callback:
                progress_callback(model_id, task.download_progress_pct)

            if catalog_entry.get("clip_filename"):
                t_clip_start = time.time()
                clip_downloaded = hf_hub_download(
                    repo_id=catalog_entry["repo_id"],
                    filename=catalog_entry["clip_filename"],
                    local_dir=target_dir_abs,
                    token=hf_token,
                    resume_download=True,
                )
                t_clip_elapsed = max(0.001, time.time() - t_clip_start)
                clip_bytes = os.path.getsize(clip_downloaded) if os.path.exists(clip_downloaded) else 0
                clip_mb = round(clip_bytes / (1024 * 1024), 2)
                clip_speed = round(clip_mb / t_clip_elapsed, 2)
                print(f"[ModelDownloader] {model_id}: CLIP mmproj 다운로드 완료 ({clip_mb} MB, 평균 {clip_speed} MB/s) → {clip_downloaded}")

            task.status = DownloadStatusEnum.COMPLETED
            task.download_progress_pct = 100.0
            print(f"[ModelDownloader] {model_id}: ✅ 다운로드 완료 (총 저장 경로: {target_dir_abs})")
            if progress_callback:
                progress_callback(model_id, 100.0)

        except ImportError:
            task.status = DownloadStatusEnum.FAILED
            task.error_message = (
                "huggingface_hub 패키지가 설치되어 있지 않습니다. "
                "'uv add huggingface_hub' 실행 권장."
            )
            print(f"[ModelDownloader] {model_id}: ❌ {task.error_message}")
        except Exception as e:
            task.status = DownloadStatusEnum.FAILED
            task.error_message = str(e)
            print(f"[ModelDownloader] {model_id}: ❌ 다운로드 실패 → {e}")

        return task

    def download_all_models(
        self,
        model_ids: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        skip_existing: bool = True,
        ignore_vram_check: bool = False,
    ) -> Dict[str, ModelDownloadTask]:
        targets = model_ids or list(self.catalog.keys())
        results: Dict[str, ModelDownloadTask] = {}

        for i, mid in enumerate(targets, 1):
            print(f"\n[ModelDownloader] === [{i}/{len(targets)}] {mid} ===")
            task = self.download_model(
                mid, progress_callback=progress_callback, force=not skip_existing, ignore_vram_check=ignore_vram_check
            )
            results[mid] = task

        return results


    def ensure_model_available(
        self,
        model_id: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> str:
        model_id = self.config_manager.resolve_model_id(model_id)
        catalog_entry = self.catalog.get(model_id)
        if not catalog_entry:
            raise ValueError(f"Unknown model_id: {model_id}")

        target_path = os.path.join(
            self.base_dir, catalog_entry["target_dir"], catalog_entry["filename"]
        )

        if os.path.isfile(target_path):
            return target_path

        task = self.download_model(model_id, progress_callback=progress_callback)
        if task.status in (DownloadStatusEnum.COMPLETED, DownloadStatusEnum.SKIPPED):
            return target_path
        else:
            raise FileNotFoundError(
                f"모델 다운로드 실패 ({model_id}): {task.error_message}"
            )
