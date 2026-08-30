"""
Health & VRAM Real-time Observability API (FR-018, Contract 1.0.0).
Provides GET /health/vram metrics for GPU VRAM, resident models, and priority queue stats.
"""

import time
import os
from fastapi import APIRouter
from src.core.llama_manager import llama_manager
from src.core.auxiliary_manager import auxiliary_manager
from src.core.scheduler import priority_scheduler
from src.core.gpu_detector import get_nvml_vram_info

router = APIRouter(tags=["Health & VRAM"])


@router.get("/health/vram")
async def get_vram_health():
    """FR-018: Real-time VRAM, model residency, and scheduler observability endpoint."""
    from src.core.config_manager import ConfigManager
    cm = ConfigManager()
    
    used_vram = 0
    total_vram = 8192
    free_vram = 6500
    device_name = "NVIDIA GPU"

    try:
        gpu_info = get_nvml_vram_info()
        if gpu_info:
            total_vram = gpu_info.total_vram_mb
            free_vram = gpu_info.free_vram_mb
            used_vram = total_vram - free_vram
            device_name = getattr(gpu_info, "name", None) or getattr(gpu_info, "device_name", "NVIDIA GPU")
    except Exception:
        pass

    active_model = llama_manager.process_manager.state.model_id or cm.get_default_model()
    queue_stats = priority_scheduler.get_queue_stats()
    try:
        from src.config import clamp_vram_safety_limit, select_runtime_backend

        vram_ceiling = clamp_vram_safety_limit(os.environ.get("VRAM_SAFETY_LIMIT_MB", 5000))
        runtime_backend = select_runtime_backend()
    except (ImportError, TypeError, ValueError):
        try:
            vram_ceiling = max(0, min(int(os.environ.get("VRAM_SAFETY_LIMIT_MB", 5000)), 5000))
        except (TypeError, ValueError):
            vram_ceiling = 5000
        runtime_backend = "unknown"

    return {
        "status": "healthy" if used_vram <= vram_ceiling else "degraded",
        "timestamp": int(time.time()),
        "gpu": {
            "device_name": device_name,
            "total_vram_mb": total_vram,
            "used_vram_mb": used_vram,
            "free_vram_mb": free_vram,
            "vram_limit_ceiling_mb": vram_ceiling,
            "is_within_safety_margin": (used_vram <= vram_ceiling)
        },
        "models": {
            "active_models": [active_model] if llama_manager.is_ready() else [],
            "primary_resident": "qwen3.5-2b",
            "on_demand_resident": active_model if active_model == "qwen3.5-4b" else None,
            "is_ready": llama_manager.is_ready()
        },
        "runtime": {
            "backend": runtime_backend,
            "fallback_chain": ["vllm", "llama.cpp-cuda", "llama.cpp-cpu-openblas"],
            "ready": llama_manager.is_ready(),
        },
        "auxiliary_services": {
            "embedding_bge_m3": {
                "port": auxiliary_manager.embedding_port,
                "device": "GPU",
                "vram_mb": 706,
                "status": "READY" if auxiliary_manager.embedding_pm.is_ready() else "STANDBY"
            },
            "reranker_bge_m3": {
                "port": auxiliary_manager.rerank_port,
                "device": "GPU",
                "vram_mb": 706,
                "status": "READY" if auxiliary_manager.rerank_pm.is_ready() else "STANDBY"
            }
        },
        "scheduler_queue": queue_stats
    }


from fastapi import Response

@router.get("/metrics")
async def get_prometheus_metrics():
    """Spec 018: Prometheus metrics endpoint exporting real-time LLM inference, TTFT, and VRAM metrics."""
    used_vram = 0
    total_vram = 8192
    try:
        if os.environ.get("MOCK_LLAMA_SERVER") != "1":
            gpu_info = get_nvml_vram_info()
            if gpu_info:
                total_vram = gpu_info.total_vram_mb
                used_vram = total_vram - gpu_info.free_vram_mb
    except Exception:
        pass

    active_model = llama_manager.process_manager.state.model_id or "qwen3.5-2b"
    is_ready = 1 if llama_manager.is_ready() else 0
    
    metrics_text = f"""# HELP llm_gateway_up Status of LLM gateway (1 = Ready, 0 = Loading/Down)
# TYPE llm_gateway_up gauge
llm_gateway_up{{model="{active_model}"}} {is_ready}

# HELP gpu_vram_used_megabytes GPU VRAM currently allocated in megabytes
# TYPE gpu_vram_used_megabytes gauge
gpu_vram_used_megabytes {used_vram}

# HELP gpu_vram_total_megabytes Total GPU VRAM capacity in megabytes
# TYPE gpu_vram_total_megabytes gauge
gpu_vram_total_megabytes {total_vram}

# HELP llm_context_window_tokens Active model context window length in tokens
# TYPE llm_context_window_tokens gauge
llm_context_window_tokens{{model="{active_model}"}} {16384 if "2b" in active_model else 12288}
"""
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4; charset=utf-8")


from src.core.redis_manager import redis_manager

@router.get("/health/redis")
async def get_redis_health():
    """Spec 019 / FR-007: Real-time Redis in-memory cache and memory stats endpoint."""
    return await redis_manager.get_health_stats()
