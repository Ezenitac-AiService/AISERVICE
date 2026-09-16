import pytest
from src.core.process_manager import ProcessManager, LlamaServerBinaryInfo
from src.core.gpu_detector import detect_hardware_capabilities

def test_resident_processes_cli_syntax():
    """T015 / FR-074: Validate strict C++ llama-server CLI syntax for 4 resident processes."""
    pm = ProcessManager(port=8089)
    binary_info = LlamaServerBinaryInfo(
        binary_path="/usr/local/bin/llama-server",
        is_cuda_enabled=True,
        build_source="LOCAL_BIN"
    )
    profile = detect_hardware_capabilities(forced_compute_cap=8.6, forced_vram_mb=12288)

    # 1. 9B Synthesis on 8089 (32K)
    cmd_9b = pm.build_server_command(
        binary_info=binary_info,
        model_file="/app/models/qwen3.5-9b/Qwen3.5-9B-Instruct-Q4_K_M.gguf",
        model_id="qwen3.5-9b",
        n_ctx=32768,
        port=8089,
        hardware_profile=profile
    )
    assert "--host" in cmd_9b
    host_idx_9b = cmd_9b.index("--host")
    assert cmd_9b[host_idx_9b + 1] == "127.0.0.1", "Must strictly bind to 127.0.0.1"
    assert "0.0.0.0" not in cmd_9b, "0.0.0.0 must not be present"
    assert "-np" in cmd_9b and cmd_9b[cmd_9b.index("-np") + 1] == "1"
    assert "-b" in cmd_9b and cmd_9b[cmd_9b.index("-b") + 1] == "512"
    assert "-ub" in cmd_9b and cmd_9b[cmd_9b.index("-ub") + 1] == "512"
    assert "-ctk" in cmd_9b and cmd_9b[cmd_9b.index("-ctk") + 1] == "q8_0"
    assert "-ctv" in cmd_9b and cmd_9b[cmd_9b.index("-ctv") + 1] == "q8_0"
    assert "--ctk" not in cmd_9b, "Double-dash --ctk causes llama-server crash"
    assert "--ctv" not in cmd_9b, "Double-dash --ctv causes llama-server crash"
    assert "-fa" in cmd_9b
    assert "--cache-prompt" in cmd_9b
    assert "--ctx-shift" in cmd_9b

    # 2. 4B Router on 8088 (8K)
    cmd_4b = pm.build_server_command(
        binary_info=binary_info,
        model_file="/app/models/qwen3.5-4b/Qwen3.5-4B-Instruct-Q4_K_M.gguf",
        model_id="qwen3.5-4b",
        n_ctx=8192,
        port=8088,
        hardware_profile=profile
    )
    assert cmd_4b[cmd_4b.index("--host") + 1] == "127.0.0.1"
    assert cmd_4b[cmd_4b.index("--port") + 1] == "8088"
    assert "-np" in cmd_4b and cmd_4b[cmd_4b.index("-np") + 1] == "1"
    assert "-b" in cmd_4b and cmd_4b[cmd_4b.index("-b") + 1] == "512"
    assert "-ub" in cmd_4b and cmd_4b[cmd_4b.index("-ub") + 1] == "512"
    assert "-ctk" in cmd_4b and "-ctv" in cmd_4b

    # 3. BGE-M3 on 8090 (Embedding)
    cmd_emb = pm.build_server_command(
        binary_info=binary_info,
        model_file="/app/models/bge-m3/bge-m3-q8_0.gguf",
        model_id="bge-m3",
        n_ctx=2048,
        port=8090,
        target_preset={"task_type": "embedding"},
        hardware_profile=profile
    )
    assert cmd_emb[cmd_emb.index("--host") + 1] == "127.0.0.1"
    assert cmd_emb[cmd_emb.index("--port") + 1] == "8090"
    assert "--embedding" in cmd_emb

    # 4. BGE-Reranker on 8091 (Reranker)
    cmd_rerank = pm.build_server_command(
        binary_info=binary_info,
        model_file="/app/models/bge-reranker-v2-m3/bge-reranker-v2-m3-q8_0.gguf",
        model_id="bge-reranker-v2-m3",
        n_ctx=2048,
        port=8091,
        target_preset={"task_type": "rerank"},
        hardware_profile=profile
    )
    assert cmd_rerank[cmd_rerank.index("--host") + 1] == "127.0.0.1"
    assert cmd_rerank[cmd_rerank.index("--port") + 1] == "8091"
    assert "--reranking" in cmd_rerank
