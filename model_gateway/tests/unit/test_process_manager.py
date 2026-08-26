"""Unit tests for ProcessManager Gemma 4 MMProj preset catalog and CLI argument generation.

Feature: 015-gemma4-model-loading-fix
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from src.core.process_manager import ProcessManager, ProcessStatusEnum, LlamaServerBinaryInfo


def test_gemma4_preset_catalog_bindings():
    """Verify that Gemma 4 presets contain the mandatory clip MMProj projector file definitions."""
    pm = ProcessManager()
    
    assert "gemma4-e2b" in pm.model_presets
    assert pm.model_presets["gemma4-e2b"]["clip"] == "models/gemma4-e2b/mmproj-gemma-4-E2B-it-BF16.gguf"
    
    assert "gemma4-e4b" in pm.model_presets
    assert pm.model_presets["gemma4-e4b"]["clip"] == "models/gemma4-e4b/mmproj-gemma-4-E4B-it-BF16.gguf"
    
    assert "gemma4-12b" in pm.model_presets
    assert pm.model_presets["gemma4-12b"]["clip"] == "models/gemma4-12b/mmproj-gemma-4-12B-it-BF16.gguf"


@pytest.mark.asyncio
async def test_spawn_process_injects_mmproj_cli_arg_standalone():
    """Verify that standalone llama-server command line includes --mmproj when MMProj projector file exists."""
    pm = ProcessManager(port=8099)
    
    fake_binary_info = LlamaServerBinaryInfo(
        binary_path="/usr/local/bin/llama-server",
        build_source="CMAKE_CUDA_BUILD",
        is_cuda_enabled=True,
        exists=True
    )
    
    with patch.object(pm, "verify_and_build_llama_server", return_value=fake_binary_info), \
         patch("os.path.exists", return_value=True), \
         patch("asyncio.create_subprocess_exec") as mock_exec:
        
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stdout = MagicMock()
        mock_exec.return_value = mock_process
        
        await pm.spawn_process("gemma4-e2b")
        
        mock_exec.assert_called_once()
        cmd = mock_exec.call_args[0]
        
        # Verify --mmproj is in CLI args
        assert "--mmproj" in cmd
        mmproj_idx = cmd.index("--mmproj")
        assert cmd[mmproj_idx + 1].endswith("models/gemma4-e2b/mmproj-gemma-4-E2B-it-BF16.gguf")


@pytest.mark.asyncio
async def test_spawn_process_injects_clip_model_path_cli_arg_python_fallback():
    """Verify that llama_cpp.server python module command line includes --clip_model_path when MMProj exists."""
    pm = ProcessManager(port=8099)
    
    fake_binary_info = LlamaServerBinaryInfo(
        binary_path="python",
        build_source="PYTHON_MODULE_FALLBACK",
        is_cuda_enabled=True,
        exists=True
    )
    
    with patch.object(pm, "verify_and_build_llama_server", return_value=fake_binary_info), \
         patch("os.path.exists", return_value=True), \
         patch("asyncio.create_subprocess_exec") as mock_exec:
        
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stdout = MagicMock()
        mock_exec.return_value = mock_process
        
        await pm.spawn_process("gemma4-e2b")
        
        mock_exec.assert_called_once()
        cmd = mock_exec.call_args[0]
        
        # Verify --clip_model_path is in CLI args
        assert "--clip_model_path" in cmd
        clip_idx = cmd.index("--clip_model_path")
        assert cmd[clip_idx + 1].endswith("models/gemma4-e2b/mmproj-gemma-4-E2B-it-BF16.gguf")


# T009 / US2: CMake -DGGML_CUDA=ON flag injection verification

@patch("shutil.which", return_value=None)  # No llama-server in PATH
@patch("os.path.exists")
@patch("subprocess.run")
def test_verify_and_build_llama_server_cmake_cuda_flag(mock_run, mock_exists, mock_which):
    """T009: verify_and_build_llama_server()는 CMake 빌드 시 -DGGML_CUDA=ON 플래그를 주입해야 한다."""
    def exists_side_effect(path):
        if path.endswith("llama-server") and ".bin" in path:
            return False  # local binary doesn't exist
        if path.endswith("CMakeLists.txt"):
            return True  # llama.cpp source exists
        if "build/bin/llama-server" in path:
            return True  # built binary exists
        return False

    mock_exists.side_effect = exists_side_effect

    # mock subprocess.run calls for cmake
    mock_run.return_value = MagicMock(returncode=0)

    with patch("shutil.copy2"), patch("os.chmod"), patch("os.makedirs"):
        result = ProcessManager.verify_and_build_llama_server()

    # Verify cmake -B build -DGGML_CUDA=ON was called
    cmake_calls = [c for c in mock_run.call_args_list if "cmake" in str(c)]
    assert len(cmake_calls) >= 1, "CMake should have been invoked"

    # Check the first cmake call includes -DGGML_CUDA=ON
    first_cmake_args = cmake_calls[0][0][0]  # positional args
    assert "-DGGML_CUDA=ON" in first_cmake_args, \
        f"CMake build must include -DGGML_CUDA=ON flag, got: {first_cmake_args}"


@pytest.mark.asyncio
async def test_poll_server_health_dynamic_timeout_scaling():
    """T004 [US1]: poll_server_health dynamic timeout scaling up to 60s for large n_ctx and file_size_mb."""
    from src.core.process_manager import poll_server_health

    with patch("httpx.AsyncClient.get") as mock_get, \
         patch("os.environ.get", return_value=None):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        res = await poll_server_health(port=8081, file_size_mb=3000.0, n_ctx=10240)
        assert res is True


def test_process_manager_dual_compatibility_calculate_base_vram():
    """T002/T005: Verify calculate_base_vram_mb works on class and instance calls, handling invalid inputs gracefully."""
    pm = ProcessManager()

    # 1. Class static call
    res_class = ProcessManager.calculate_base_vram_mb("invalid/path/nonexistent.gguf")
    assert res_class == 6000

    # 2. Instance call
    res_inst = pm.calculate_base_vram_mb("invalid/path/nonexistent.gguf")
    assert res_inst == 6000

    # 3. Positional instance object pass protection
    res_accidental = ProcessManager.calculate_base_vram_mb(pm, "invalid/path/nonexistent.gguf")
    assert res_accidental == 6000


def test_process_manager_dual_compatibility_force_kill_zombie_llama_servers():
    """T002/T005: Verify force_kill_zombie_llama_servers works on class and instance calls."""
    pm = ProcessManager()

    # Should not raise AttributeError or TypeError
    ProcessManager.force_kill_zombie_llama_servers()
    pm.force_kill_zombie_llama_servers()
    pm.force_kill_zombie_llama_servers((8081, 8089))
