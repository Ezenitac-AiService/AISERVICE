"""
Integration tests for dynamic llama-server process switching and VRAM release (T007).
Tests FR-004 (SIGTERM/SIGKILL escalation) and T006 (HTTP health check polling).
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.core.process_manager import ProcessManager, ProcessStatusEnum, ProcessState
from src.core.llama_manager import LlamaManager
from src.core.config_manager import ConfigManager


@pytest.fixture
def config_manager():
    return ConfigManager()


@pytest.fixture
def process_manager():
    return ProcessManager(port=8081)


class TestProcessManagerSwitching:
    """FR-004: 동적 프로세스 스위칭 및 VRAM 해제 통합 테스트."""

    @pytest.mark.asyncio
    async def test_stop_process_returns_unloaded_state(self, process_manager):
        """프로세스 미실행 상태에서 stop 호출 시 UNLOADED 반환."""
        state = await process_manager.stop_process()
        assert state.status == ProcessStatusEnum.UNLOADED

    @pytest.mark.asyncio
    async def test_spawn_unknown_model_returns_error(self, process_manager):
        """알 수 없는 모델 ID로 spawn 시 ERROR 반환."""
        state = await process_manager.spawn_process("nonexistent-model", 4096)
        assert state.status == ProcessStatusEnum.ERROR
        assert "Unknown model_id" in state.error_message

    @pytest.mark.asyncio
    async def test_spawn_missing_model_file_returns_error(self, process_manager):
        """모델 파일이 없는 상태에서 spawn 시 ERROR 반환."""
        with patch("os.path.exists", return_value=False):
            state = await process_manager.spawn_process("qwen3.5-2b", 4096)
            assert state.status == ProcessStatusEnum.ERROR
            assert "not found" in state.error_message.lower() or "Model file" in state.error_message

    def test_vram_estimation(self, process_manager):
        """VRAM 추정 계산 정확성."""
        vram = process_manager.estimate_vram_usage("gemma4-12b", 4096)
        assert isinstance(vram, int) and vram > 5000

    @pytest.mark.asyncio
    async def test_vram_oom_check(self, process_manager):
        """VRAM 초과 시 OOM 에러."""
        # gemma4-12b는 9500MB, context 확대 시 제한 초과 가능
        state = await process_manager.spawn_process("gemma4-12b", 12000)
        # With n_ctx=12000, extra = (12000-4096)*0.5 = 3952 -> total = 9500+3952 = 13452
        # 13452 > 11264+2000=13264 -> OOM
        assert state.status == ProcessStatusEnum.ERROR
        assert "CUDA OOM" in state.error_message

    def test_downloading_status_exists(self):
        """DOWNLOADING 상태가 ProcessStatusEnum에 존재."""
        assert ProcessStatusEnum.DOWNLOADING == "DOWNLOADING"


class TestLlamaManagerHealthCheck:
    """T006: HTTP 헬스체크 폴링 및 자동 다운로드 연동 통합 테스트."""

    @pytest.mark.asyncio
    async def test_wait_for_ready_timeout(self, config_manager):
        """서버가 없으면 _wait_for_ready가 타임아웃으로 False 반환."""
        manager = LlamaManager(config_manager, port=19999)  # 비활성 포트
        result = await manager._wait_for_ready(timeout=1.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_load_model_with_download_unknown_model(self, config_manager):
        """알 수 없는 모델 로드 시도 시 에러 상태 반환."""
        manager = LlamaManager(config_manager, port=19999)
        state = await manager.load_model_with_download("nonexistent-model", 4096)
        assert state.status == ProcessStatusEnum.ERROR
