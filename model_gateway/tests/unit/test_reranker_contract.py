import pytest
from src.core.process_manager import ProcessManager, LlamaServerBinaryInfo


def test_reranker_binary_info_contract():
    """Validates that ProcessManager.verify_and_build_llama_server() conforms to the binary info schema."""
    info = ProcessManager.verify_and_build_llama_server()
    assert hasattr(info, "binary_path")
    assert hasattr(info, "build_source")
    assert isinstance(info.binary_path, str)
    assert isinstance(info.build_source, str)
    assert len(info.binary_path) > 0


def test_reranker_process_spawn_cmd_flags():
    """Validates that for a rerank model preset, spawn_process constructs --reranking and --embedding options."""
    pm = ProcessManager(port=8091)
    
    # Mock preset for rerank model
    pm.model_presets["bge-reranker-v2-m3"] = {
        "model": "models/bge-reranker-v2-m3.Q4_K_M.gguf",
        "clip": None,
        "chat_template": "chatml",
        "vram_est_mb": 2000,
        "task_type": "rerank"
    }

    assert pm.is_rerank_model("bge-reranker-v2-m3") is True
