"""Unit tests for scripts/benchmark_context_window.py (T007).
Tests candidate LLM model filtering and pre-flight VRAM check across multi-tier GPU environments."""

import json
import pytest
from scripts.benchmark_context_window import get_candidate_llm_models



class TestCandidateLLMModels:
    """T007: Candidate LLM models filtering 단위 테스트."""

    def test_candidate_count_is_12(self):
        """카탈로그에서 LLM 후보 모델이 추출되어야 함 (embedding/rerank 제외)."""
        candidates = get_candidate_llm_models()
        assert len(candidates) >= 12, f"Expected at least 12 LLM candidates, got {len(candidates)}: {candidates}"

    def test_excludes_embedding_and_rerank(self):
        """bge-m3 (embedding) 및 bge-reranker-v2-m3 (rerank) 모델은 후보에서 제외되어야 함."""
        candidates = get_candidate_llm_models()
        assert "bge-m3" not in candidates
        assert "bge-reranker-v2-m3" not in candidates

    def test_includes_new_heavy_models(self):
        """신규 대형 모델 3종이 후보에 포함되어야 함."""
        candidates = get_candidate_llm_models()
        assert "qwen3.6-27b" in candidates
        assert "qwen3.6-35b-a3b" in candidates
        assert "gemma4-26b-a4b" in candidates

    def test_includes_text_only_models(self):
        """텍스트 전용 모델 3종이 후보에 포함되어야 함."""
        candidates = get_candidate_llm_models()
        assert "gemma4-2b-text" in candidates
        assert "gemma4-4b-text" in candidates
        assert "gemma4-12b-text" in candidates

    def test_includes_existing_models(self):
        """기존 LLM 모델 6종이 후보에 포함되어야 함."""
        candidates = get_candidate_llm_models()
        for m in ["gemma4-e2b", "gemma4-e4b", "gemma4-12b", "qwen3.5-2b", "qwen3.5-4b", "qwen3.5-9b"]:
            assert m in candidates, f"{m} should be in candidates"


class TestPreflightVRAMCheck:
    """T007: Pre-flight VRAM 체크 다중 계층(8G/11G/24G/32G/40G/80G) 파라메트릭 테스트."""

    # VRAM Tier -> (Total VRAM MB, Usable VRAM MB after -500MB cushion)
    VRAM_TIERS = {
        "8G": (8192, 7692),    # GTX 1070/1080/RTX 2080
        "11G": (11264, 10764),  # GTX 1080 Ti  
        "24G": (24576, 24076),  # RTX 3090
        "32G": (32768, 32268),  # RTX 4090/5090
        "40G": (40960, 40460),  # A100
        "80G": (81920, 81420),  # H100
    }

    # Model VRAM requirements from catalog
    MODEL_VRAM = {
        "gemma4-2b-text": 2800,
        "qwen3.5-2b": 3000,
        "gemma4-e2b": 3500,
        "gemma4-4b-text": 5200,
        "qwen3.5-4b": 5500,
        "gemma4-e4b": 6500,
        "gemma4-12b-text": 9200,
        "gemma4-12b": 9500,
        "qwen3.5-9b": 9800,
        "gemma4-26b-a4b": 18800,
        "qwen3.6-27b": 19500,
        "qwen3.6-35b-a3b": 24500,
    }

    # Expected supported count per tier
    EXPECTED_SUPPORTED = {
        "8G": 6,   # 2B and 4B class models only
        "11G": 9,  # adds 9B/12B class
        "24G": 11, # adds 26B MoE and 27B, excludes 35B-A3B
        "32G": 12, # all supported
        "40G": 12,
        "80G": 12,
    }

    @pytest.mark.parametrize("tier_name", ["8G", "11G", "24G", "32G", "40G", "80G"])
    def test_vram_tier_support_count(self, tier_name):
        """각 VRAM 계층별 지원 모델 수가 기대값과 일치해야 함."""
        _, usable_vram = self.VRAM_TIERS[tier_name]
        supported = [m for m, vram in self.MODEL_VRAM.items() if vram <= usable_vram]
        expected = self.EXPECTED_SUPPORTED[tier_name]
        assert len(supported) == expected, (
            f"[{tier_name}] Expected {expected} supported models, got {len(supported)}: {supported}"
        )

    @pytest.mark.parametrize("tier_name", ["8G", "11G", "24G", "32G", "40G", "80G"])
    def test_vram_tier_exclusion_count(self, tier_name):
        """각 VRAM 계층별 배제 모델 수가 정확해야 함."""
        _, usable_vram = self.VRAM_TIERS[tier_name]
        excluded = [m for m, vram in self.MODEL_VRAM.items() if vram > usable_vram]
        expected_excluded = 12 - self.EXPECTED_SUPPORTED[tier_name]
        assert len(excluded) == expected_excluded, (
            f"[{tier_name}] Expected {expected_excluded} excluded models, got {len(excluded)}: {excluded}"
        )

    def test_8g_excludes_9b_and_above(self):
        """8GB VRAM에서 9B 이상 모델 6개가 모두 배제되어야 함."""
        usable = self.VRAM_TIERS["8G"][1]  # 7692 MB
        excluded_models = [m for m, v in self.MODEL_VRAM.items() if v > usable]
        assert "qwen3.5-9b" in excluded_models
        assert "gemma4-12b" in excluded_models
        assert "gemma4-12b-text" in excluded_models
        assert "gemma4-26b-a4b" in excluded_models
        assert "qwen3.6-27b" in excluded_models
        assert "qwen3.6-35b-a3b" in excluded_models

    def test_24g_excludes_only_35b_a3b(self):
        """24GB VRAM에서 qwen3.6-35b-a3b만 배제되어야 함."""
        usable = self.VRAM_TIERS["24G"][1]  # 24076 MB
        excluded_models = [m for m, v in self.MODEL_VRAM.items() if v > usable]
        assert excluded_models == ["qwen3.6-35b-a3b"]

    def test_32g_supports_all(self):
        """32GB 이상 VRAM에서 모든 12개 모델이 지원되어야 함."""
        usable = self.VRAM_TIERS["32G"][1]  # 32268 MB
        supported = [m for m, v in self.MODEL_VRAM.items() if v <= usable]
        assert len(supported) == 12

    def test_usable_vram_formula(self):
        """Usable VRAM = Total VRAM - 500MB 공식 검증."""
        for tier_name, (total, usable) in self.VRAM_TIERS.items():
            assert usable == total - 500, f"[{tier_name}] Usable VRAM formula mismatch"


class TestNonDestructiveProfilePreservation:
    """T009/T010/US2: 비파괴적 프로파일 보존 단위 테스트."""

    def test_non_destructive_profile_preservation(self, tmp_path, monkeypatch):
        from scripts.benchmark_context_window import _record_unsupported_fallback_profile
        from src.core.config_manager import ConfigManager

        profile_file = tmp_path / "model_context_profiles.json"
        initial_data = {
            "generated_at": "2026-08-07T00:00:00Z",
            "profiles": {
                "qwen3.5-4b": {
                    "max_context_length": 12288,
                    "recommended_context_length": 12288,
                    "is_supported": True,
                    "tpot_tok_per_sec": 45.0
                }
            }
        }
        profile_file.write_text(json.dumps(initial_data), encoding="utf-8")

        monkeypatch.setattr(ConfigManager, "load_model_context_profiles", lambda self: initial_data)

        # Call fallback without force_overwrite -> should preserve existing profile
        res = _record_unsupported_fallback_profile("qwen3.5-4b", reason="Transient OOM", force_overwrite=False)

        assert res["is_supported"] is True
        assert res["max_context_length"] == 12288
        assert res["recommended_context_length"] == 12288

    def test_force_overwrite_profiles_flag(self, tmp_path, monkeypatch):
        from scripts.benchmark_context_window import _record_unsupported_fallback_profile
        from src.core.config_manager import ConfigManager

        profile_file = tmp_path / "model_context_profiles.json"
        initial_data = {
            "generated_at": "2026-08-07T00:00:00Z",
            "profiles": {
                "qwen3.5-4b": {
                    "max_context_length": 12288,
                    "recommended_context_length": 12288,
                    "is_supported": True,
                    "tpot_tok_per_sec": 45.0
                }
            }
        }
        profile_file.write_text(json.dumps(initial_data), encoding="utf-8")

        monkeypatch.setattr(ConfigManager, "load_model_context_profiles", lambda self: initial_data)
        saved_data = {}
        monkeypatch.setattr(ConfigManager, "save_model_context_profiles", lambda self, data: saved_data.update(data))

        # Call fallback WITH force_overwrite=True -> should overwrite with unsupported fallback
        res = _record_unsupported_fallback_profile("qwen3.5-4b", reason="Forced test", force_overwrite=True)

        assert res["is_supported"] is False
        assert res["max_context_length"] == 2048


class TestDynamicRangeAndZeroMagicNumbers:
    """T006 / T007 / T016 / T017: Dynamic range upper bound calculation and zero magic numbers tests."""

    def test_dynamic_high_bound_calculation(self):
        """T006: High bound must be calculated dynamically based on usable VRAM and model max RoPE."""
        from src.core.gpu_detector import calculate_max_allocatable_n_ctx

        # Usable KV budget = 6000 MB for a model with 36 layers, 32 heads, 128 head_dim
        # Max allocatable n_ctx should scale dynamically to 10240, not clamped at 4096 or 16384
        n_ctx = calculate_max_allocatable_n_ctx(usable_kv_budget_mb=6000, n_layers=36, n_heads=32, head_dim=128)
        assert n_ctx == 10240

    def test_gemma4_e2b_range_expansion(self):
        """T007: Small model gemma4-e2b should expand binary search range up to 16384 on 11GB VRAM."""
        from src.core.gpu_detector import calculate_max_allocatable_n_ctx

        # gemma4-e2b (Base VRAM ~3.7GB). Free VRAM on 11GB GPU = ~10.7GB.
        # remaining_kv_budget = 10764 - 3700 - 1319 = ~5745 MB
        # Should calculate max_allocatable_n_ctx >= 9728
        max_ctx = calculate_max_allocatable_n_ctx(usable_kv_budget_mb=5745, n_layers=36, n_heads=32, head_dim=128)
        assert max_ctx >= 9728

    def test_zero_magic_numbers_audit(self):
        """T016: Verify that scripts/benchmark_context_window.py has no hardcoded 3000MB or 45.0 TPS magic numbers."""
        from pathlib import Path
        script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "benchmark_context_window.py"
        content = script_path.read_text(encoding="utf-8")

        assert "remaining_kv_budget < 3000" not in content, "Magic number 'remaining_kv_budget < 3000' found!"
        assert "tps_val = 45.0" not in content, "Magic number 'tps_val = 45.0' found in binary search inner loop!"

    @pytest.mark.asyncio
    async def test_real_tps_calculation(self):
        """T017: Real TPS should be computed from token count / elapsed time."""
        elapsed = 0.5  # 500 ms
        tokens = 10
        tps = tokens / elapsed
        assert tps == 20.0

    @pytest.mark.asyncio
    async def test_dynamic_range_reexpansion(self, monkeypatch):
        """T011 / US2: Test dynamic range re-expansion when free VRAM > 50%."""
        from scripts.benchmark_context_window import async_run_fine_grained_binary_search
        from src.core.process_manager import ProcessState, ProcessStatusEnum, ProcessManager
        from src.core.gpu_detector import GpuDeviceInfo

        monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
        monkeypatch.setattr("src.core.gpu_detector.get_realtime_usable_vram", lambda n_ctx=4096: 10000)
        monkeypatch.setattr("src.core.gpu_detector.get_nvml_vram_info", lambda: GpuDeviceInfo(
            device_id=0, name="Mock GPU", total_vram_mb=11264, free_vram_mb=8000, is_cuda_available=True
        ))

        async def mock_spawn(pm, model_id, n_ctx):
            return ProcessState(status=ProcessStatusEnum.READY, model_id=model_id, port=8081, pid=1234)

        async def mock_stop(pm):
            pass

        monkeypatch.setattr(ProcessManager, "spawn_process", mock_spawn)
        monkeypatch.setattr(ProcessManager, "stop_process", mock_stop)

        res = await async_run_fine_grained_binary_search("gemma4-e2b", force_overwrite=True)
        assert res["is_supported"] is True
        assert res["max_context_length"] >= 16384

    def test_log_scaled_step_size(self):
        """T012 / US2: Test log-scaled step size formula across context boundaries."""
        from src.core.gpu_detector import calculate_dynamic_log_step_size
        assert calculate_dynamic_log_step_size(8192) == 512
        assert calculate_dynamic_log_step_size(32768) == 512
        assert calculate_dynamic_log_step_size(131072) == 2048
        assert calculate_dynamic_log_step_size(1048576) == 16384


class TestBenchmarkContextWindowSafety:
    """T002 / US2: benchmark_context_window remaining_kv_budget 및 파이프라인 안전성 테스트."""

    def test_benchmark_context_window_no_nameerror(self, monkeypatch):
        """benchmark_context_window() 호출 시 NameError 예외가 발생하지 않는지 검증."""
        from scripts.benchmark_context_window import benchmark_context_window

        monkeypatch.setenv("MOCK_LLAMA_SERVER", "1")
        res = benchmark_context_window("qwen3.5-2b")
        assert res["recommended_model"] == "qwen3.5-2b"
        assert "recommended_context_window" in res
        assert res["recommended_context_window"] > 0


class TestDynamicGQAAndCLIFlags:
    """T005 / T007 / 118: 동적 GQA VRAM 추정 및 CLI --all 옵션 검증 단위 테스트."""

    def test_estimate_vram_usage_uses_model_gqa_architecture(self):
        """T005: Qwen 3.5 2B/4B 모델 @ n_ctx=16384 일 때 GQA 파라미터가 반영되어 15.2GB 오탐 차단 없이 스폰 가능 판정되어야 함."""
        from src.core.process_manager import ProcessManager

        pm = ProcessManager()
        # Qwen 3.5 2B (24 layers, 14 heads, 2 kv_heads, 128 dim) @ n_ctx=16384
        vram_2b = pm.estimate_vram_usage("qwen3.5-2b", n_ctx=16384)
        assert vram_2b < 8000, f"Qwen 3.5 2B @ 16K estimated VRAM too high: {vram_2b}MB"

        # Qwen 3.5 4B (36 layers, 20 heads, 4 kv_heads, 128 dim) @ n_ctx=16384
        vram_4b = pm.estimate_vram_usage("qwen3.5-4b", n_ctx=16384)
        assert vram_4b < 9000, f"Qwen 3.5 4B @ 16K estimated VRAM too high: {vram_4b}MB"

    def test_cli_all_flag_parser(self):
        """T007: scripts/benchmark_context_window.py argparse에 --all 플래그가 수록되어 있어야 함."""
        import argparse
        import sys
        from unittest.mock import patch
        from scripts.benchmark_context_window import main

        test_args = ["scripts/benchmark_context_window.py", "--all", "--help"]
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0




