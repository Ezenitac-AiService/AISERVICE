"""
Unit tests for src/core/model_downloader.py (T005).
Tests ModelDownloadTask, ModelDownloader catalog, availability checks, and download state tracking.
"""

import os
import tempfile
import pytest
from src.core.model_downloader import (
    ModelDownloadTask,
    ModelDownloader,
    DownloadStatusEnum,
    MODEL_DOWNLOAD_CATALOG,
)


class TestModelDownloadTask:
    """T001 Pydantic v2 ModelDownloadTask 데이터 모델 단위 테스트."""

    def test_create_pending_task(self):
        """PENDING 상태의 다운로드 태스크 생성."""
        task = ModelDownloadTask(
            model_id="qwen3.5-2b",
            repo_id="Qwen/Qwen3.5-2B-Instruct-GGUF",
            filename="qwen3.5-2b-instruct-q4_k_m.gguf",
            target_dir="models/qwen3.5-2b",
        )
        assert task.status == DownloadStatusEnum.PENDING
        assert task.download_progress_pct == 0.0
        assert task.error_message is None

    def test_create_completed_task(self):
        """COMPLETED 상태의 다운로드 태스크 생성."""
        task = ModelDownloadTask(
            model_id="gemma4-e2b",
            repo_id="lmstudio-community/gemma-4-E2B-it-GGUF",
            filename="gemma-4-E2B_q4_0-it.gguf",
            clip_filename="gemma-4-E2B-it-mmproj.gguf",
            target_dir="models/gemma4-2b",
            status=DownloadStatusEnum.COMPLETED,
            download_progress_pct=100.0,
        )
        assert task.status == DownloadStatusEnum.COMPLETED
        assert task.clip_filename == "gemma-4-E2B-it-mmproj.gguf"
        assert task.download_progress_pct == 100.0

    def test_update_task_status(self):
        """태스크 상태 업데이트 가능 여부."""
        task = ModelDownloadTask(
            model_id="qwen3.5-4b",
            repo_id="Qwen/Qwen3.5-4B-Instruct-GGUF",
            filename="qwen3.5-4b-instruct-q4_k_m.gguf",
            target_dir="models/qwen3.5-4b",
        )
        task.status = DownloadStatusEnum.DOWNLOADING
        task.download_progress_pct = 45.5
        assert task.status == DownloadStatusEnum.DOWNLOADING
        assert task.download_progress_pct == 45.5


class TestModelDownloadCatalog:
    """MODEL_DOWNLOAD_CATALOG 카탈로그 무결성 단위 테스트."""

    def test_catalog_has_six_models(self):
        """카탈로그에 모델 항목들이 정상 등록되어야 함."""
        assert len(MODEL_DOWNLOAD_CATALOG) >= 14

    def test_qwen_models_no_clip(self):
        """Qwen 3.5 모델은 CLIP mmproj가 없어야 함."""
        for model_id in ["qwen3.5-2b", "qwen3.5-4b", "qwen3.5-9b"]:
            entry = MODEL_DOWNLOAD_CATALOG[model_id]
            assert entry["clip_filename"] is None

    def test_gemma_models_have_clip(self):
        """Gemma 4 모델은 CLIP mmproj가 있어야 함."""
        for model_id in ["gemma4-e2b", "gemma4-e4b", "gemma4-12b"]:
            entry = MODEL_DOWNLOAD_CATALOG[model_id]
            assert entry["clip_filename"] is not None

    def test_all_entries_have_required_fields(self):
        """모든 카탈로그 항목에 필수 필드가 있어야 함."""
        for model_id, entry in MODEL_DOWNLOAD_CATALOG.items():
            assert "repo_id" in entry, f"{model_id}: repo_id 누락"
            assert "filename" in entry, f"{model_id}: filename 누락"
            assert "target_dir" in entry, f"{model_id}: target_dir 누락"

    def test_new_qwen36_models_no_clip(self):
        """verify qwen3.6-27b and qwen3.6-35b-a3b have clip_filename: null and requires_mmproj: false"""
        for model_id in ["qwen3.6-27b", "qwen3.6-35b-a3b"]:
            entry = MODEL_DOWNLOAD_CATALOG[model_id]
            assert entry.get("clip_filename") is None
            assert entry.get("requires_mmproj") is False

    def test_gemma4_text_only_models_no_clip(self):
        """verify gemma4-2b-text, gemma4-4b-text, gemma4-12b-text have clip_filename: null and requires_mmproj: false"""
        for model_id in ["gemma4-2b-text", "gemma4-4b-text", "gemma4-12b-text"]:
            entry = MODEL_DOWNLOAD_CATALOG[model_id]
            assert entry.get("clip_filename") is None
            assert entry.get("requires_mmproj") is False

    def test_gemma4_26b_a4b_moe_model(self):
        """verify gemma4-26b-a4b has requires_mmproj: false and vram_est_mb: 18800"""
        entry = MODEL_DOWNLOAD_CATALOG["gemma4-26b-a4b"]
        assert entry.get("requires_mmproj") is False
        assert entry.get("vram_est_mb") == 18800

    def test_all_14_models_have_required_schema_fields(self):
        """verify all 14 models have: name, repo_id, filename, target_dir, model_path, default_n_ctx, vram_est_mb, requires_mmproj, quant_type, size_gb"""
        required_fields = ["name", "repo_id", "filename", "target_dir", "model_path", "default_n_ctx", "vram_est_mb", "requires_mmproj", "quant_type", "size_gb"]
        for model_id, entry in MODEL_DOWNLOAD_CATALOG.items():
            for field in required_fields:
                assert field in entry, f"{model_id}: {field} 누락"

    def test_vram_estimates_are_plausible(self):
        """verify all vram_est_mb values are >= 100 and size_gb >= 0.1"""
        for model_id, entry in MODEL_DOWNLOAD_CATALOG.items():
            assert entry["vram_est_mb"] >= 100, f"{model_id}: 비정상 vram_est_mb"
            assert entry["size_gb"] >= 0.1, f"{model_id}: 비정상 size_gb"


class TestModelDownloader:
    """ModelDownloader 엔진 단위 테스트."""

    def test_is_model_available_false_when_missing(self):
        """로컬에 모델 파일이 없으면 False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = ModelDownloader(base_dir=tmpdir)
            assert downloader.is_model_available("qwen3.5-2b") is False

    def test_is_model_available_true_when_exists(self):
        """로컬에 모델 파일이 있으면 True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 가짜 GGUF 파일 생성
            target_dir = os.path.join(tmpdir, "models", "qwen3.5-2b")
            os.makedirs(target_dir, exist_ok=True)
            fake_gguf = os.path.join(target_dir, "Qwen3.5-2B-Q4_K_M.gguf")
            with open(fake_gguf, "wb") as f:
                f.write(b"FAKE_GGUF_CONTENT")

            downloader = ModelDownloader(base_dir=tmpdir)
            assert downloader.is_model_available("qwen3.5-2b") is True

    def test_get_model_path_returns_none_when_missing(self):
        """모델 파일 미존재 시 None 반환."""
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = ModelDownloader(base_dir=tmpdir)
            assert downloader.get_model_path("qwen3.5-9b") is None

    def test_get_model_path_returns_path_when_exists(self):
        """모델 파일 존재 시 절대 경로 반환."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = os.path.join(tmpdir, "models", "gemma4-e2b")
            os.makedirs(target_dir, exist_ok=True)
            fake_gguf = os.path.join(target_dir, "gemma-4-E2B_q4_0-it.gguf")
            with open(fake_gguf, "wb") as f:
                f.write(b"FAKE_GGUF_CONTENT")

            downloader = ModelDownloader(base_dir=tmpdir)
            result = downloader.get_model_path("gemma4-e2b")
            assert result is not None
            assert result.endswith("gemma-4-E2B_q4_0-it.gguf")

            # Test alias resolution
            alias_result = downloader.get_model_path("gemma4-2b")
            assert alias_result == result

    def test_download_unknown_model_returns_failed(self):
        """알 수 없는 model_id로 다운로드 시 FAILED 상태 반환."""
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = ModelDownloader(base_dir=tmpdir)
            task = downloader.download_model("nonexistent-model")
            assert task.status == DownloadStatusEnum.FAILED
            assert "Unknown model_id" in task.error_message

    def test_download_skips_existing_file(self):
        """이미 존재하는 파일은 SKIPPED 상태로 건너뜀."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = os.path.join(tmpdir, "models", "qwen3.5-2b")
            os.makedirs(target_dir, exist_ok=True)
            fake_gguf = os.path.join(target_dir, "Qwen3.5-2B-Q4_K_M.gguf")
            with open(fake_gguf, "wb") as f:
                f.write(b"FAKE_GGUF_CONTENT")

            downloader = ModelDownloader(base_dir=tmpdir)
            task = downloader.download_model("qwen3.5-2b")
            assert task.status == DownloadStatusEnum.SKIPPED
            assert task.download_progress_pct == 100.0

    def test_download_model_without_huggingface_hub_fails_gracefully(self):
        """huggingface_hub 모듈 임포트 실패 시 FAILED 처리."""
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = ModelDownloader(base_dir=tmpdir)
            with patch.dict("sys.modules", {"huggingface_hub": None}):
                task = downloader.download_model("qwen3.5-2b")
                assert task.status == DownloadStatusEnum.FAILED
                assert "huggingface_hub" in task.error_message

    def test_ensure_model_available_raises_for_unknown(self):
        """알 수 없는 model_id로 ensure 호출 시 ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = ModelDownloader(base_dir=tmpdir)
            with pytest.raises(ValueError, match="Unknown model_id"):
                downloader.ensure_model_available("nonexistent")

    def test_ensure_model_available_returns_path_when_exists(self):
        """이미 존재하는 파일은 즉시 경로 반환."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = os.path.join(tmpdir, "models", "qwen3.5-4b")
            os.makedirs(target_dir, exist_ok=True)
            fake_gguf = os.path.join(target_dir, "Qwen3.5-4B-Q4_K_M.gguf")
            with open(fake_gguf, "wb") as f:
                f.write(b"FAKE_GGUF")

            downloader = ModelDownloader(base_dir=tmpdir)
            path = downloader.ensure_model_available("qwen3.5-4b")
            assert path.endswith("Qwen3.5-4B-Q4_K_M.gguf")

    def test_progress_callback_called(self):
        """다운로드 시 progress_callback이 호출됨."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = os.path.join(tmpdir, "models", "qwen3.5-2b")
            os.makedirs(target_dir, exist_ok=True)
            fake_gguf = os.path.join(target_dir, "Qwen3.5-2B-Q4_K_M.gguf")
            with open(fake_gguf, "wb") as f:
                f.write(b"FAKE_GGUF")

            callback_calls = []
            def cb(mid, pct):
                callback_calls.append((mid, pct))

            downloader = ModelDownloader(base_dir=tmpdir)
            downloader.download_model("qwen3.5-2b", progress_callback=cb)
            assert len(callback_calls) > 0
            assert callback_calls[0][0] == "qwen3.5-2b"


def test_verify_and_build_llama_server_resolution():
    from src.core.process_manager import ProcessManager, LlamaServerBinaryInfo
    info = ProcessManager.verify_and_build_llama_server()
    assert isinstance(info, LlamaServerBinaryInfo)
    assert info.binary_path is not None
    assert info.build_source in ("PATH", "LOCAL_BIN", "CMAKE_BUILD", "PYTHON_MODULE_FALLBACK", "OLLAMA_LIB", "SYSTEM_BIN")


def test_gemma4_mmproj_availability_check():
    """Verify that is_model_available requires BOTH main GGUF and MMProj files for Gemma 4."""
    with tempfile.TemporaryDirectory() as tmpdir:
        downloader = ModelDownloader(base_dir=tmpdir)
        target_dir = os.path.join(tmpdir, "models", "gemma4-e2b")
        os.makedirs(target_dir, exist_ok=True)
        
        main_gguf = os.path.join(target_dir, "gemma-4-E2B_q4_0-it.gguf")
        mmproj_gguf = os.path.join(target_dir, "gemma-4-E2B-it-mmproj.gguf")
        
        # Initially neither exists
        assert downloader.is_model_available("gemma4-e2b") is False
        
        # Only main GGUF exists
        with open(main_gguf, "wb") as f:
            f.write(b"MAIN_GGUF")
        assert downloader.is_model_available("gemma4-e2b") is False
        
        # Both main GGUF and MMProj exist
        with open(mmproj_gguf, "wb") as f:
            f.write(b"MMPROJ_GGUF")
        assert downloader.is_model_available("gemma4-e2b") is True

def test_model_catalog_instruct_and_text_only_specs():
    """Verify Gemma 4 text-only models require no mmproj and LLM models are quantized GGUFs."""
    text_only_models = ["gemma4-2b-text", "gemma4-4b-text", "gemma4-12b-text", "gemma4-26b-a4b"]
    for model_id in text_only_models:
        entry = MODEL_DOWNLOAD_CATALOG[model_id]
        assert entry.get("requires_mmproj") is False, f"{model_id}: requires_mmproj should be False"
        assert entry.get("clip_filename") is None, f"{model_id}: clip_filename should be None"

    # All 14 models must be quantized GGUFs (q4_k_m or q8_0)
    for model_id, entry in MODEL_DOWNLOAD_CATALOG.items():
        assert entry["filename"].endswith(".gguf"), f"{model_id}: filename must end with .gguf"
        assert entry.get("quant_type") in ("q4_k_m", "q8_0"), f"{model_id}: invalid quant_type"


def test_model_catalog_hf_urls_valid():
    """Live HTTP HEAD verification for all 14 catalog model URLs on HuggingFace Hub (T007)."""
    import urllib.request
    
    failed_urls = []
    for model_id, entry in MODEL_DOWNLOAD_CATALOG.items():
        repo_id = entry["repo_id"]
        filename = entry["filename"]
        url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 (vllm_serv_test)")
        try:
            res = urllib.request.urlopen(req, timeout=10)
            assert res.status == 200, f"{model_id}: unexpected status {res.status}"
        except Exception as e:
            failed_urls.append((model_id, url, str(e)))

    assert len(failed_urls) == 0, f"Failed HF Hub URLs: {failed_urls}"


def test_model_downloader_vram_precheck_skip():
    """T003 / US1: VRAMPrecheckResult 및 VRAM 초과 모델 사전 스킵 검증."""
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmpdir:
        downloader = ModelDownloader(base_dir=tmpdir)
        # Mock NVML returning 11264 MB VRAM
        with patch("src.core.gpu_detector.get_nvml_vram_info") as mock_gpu:
            from src.core.gpu_detector import GpuDeviceInfo
            mock_gpu.return_value = GpuDeviceInfo(
                device_id=0, name="NVIDIA GTX 1080 Ti", total_vram_mb=11264, free_vram_mb=8000, is_cuda_available=True
            )
            # gemma4-26b-a4b size ~16.9GB -> base VRAM ~19435MB + KV 1152MB = 20587MB > 11264MB
            res = downloader.check_vram_feasibility("gemma4-26b-a4b")
            assert res.is_feasible is False
            assert res.status_code == "SKIP_OOM_RISK"
            assert "물리 GPU VRAM" in res.message

            # Small model qwen3.5-2b -> base VRAM ~2000MB + KV 1152MB = 3152MB <= 11264MB
            res_pass = downloader.check_vram_feasibility("qwen3.5-2b")
            assert res_pass.is_feasible is True
            assert res_pass.status_code == "PASS"


def test_ignore_vram_check_flag_bypass():
    """T009 / US3: --ignore-vram-check 옵션 지정 시 VRAM 초과 모델 우회 검증."""
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmpdir:
        downloader = ModelDownloader(base_dir=tmpdir)
        with patch("src.core.gpu_detector.get_nvml_vram_info") as mock_gpu:
            from src.core.gpu_detector import GpuDeviceInfo
            mock_gpu.return_value = GpuDeviceInfo(
                device_id=0, name="NVIDIA GTX 1080 Ti", total_vram_mb=11264, free_vram_mb=8000, is_cuda_available=True
            )
            # ignore_vram_check=True -> returns is_feasible=True, status_code="BYPASS_WARNING"
            res = downloader.check_vram_feasibility("gemma4-26b-a4b", ignore_vram_check=True)
            assert res.is_feasible is True
            assert res.status_code == "BYPASS_WARNING"
            assert "[BYPASS VRAM Check]" in res.message

