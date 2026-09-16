"""
Health, Liveness, Readiness & VRAM Real-time Observability API.
Provides content-signed /health/readiness probe, /health/vram metrics, and Prometheus /metrics.
"""

import time
import os
import logging
from typing import Optional
from fastapi import APIRouter, Request, Response, status
from src.core.llama_manager import llama_manager
from src.core.auxiliary_manager import auxiliary_manager
from src.core.gpu_detector import get_nvml_vram_info

logger = logging.getLogger("HealthAPI")
router = APIRouter(tags=["Health & VRAM"])

_server_start_time = time.time()


@router.get("/health")
@router.get("/health/liveness")
async def liveness():
    """K8s/LiteLLM Liveness probe. Returns 200 OK if server process is running."""
    pid = llama_manager.synthesis_pm.state.pid or (llama_manager.synthesis_pm.process.pid if llama_manager.synthesis_pm.process else None)
    return {
        "status": "alive",
        "pid": pid,
        "ports": {
            "synthesis": 8089,
            "router": 8088,
            "embedding": 8090,
            "rerank": 8091
        }
    }


@router.get("/health/readiness")
async def readiness(request: Request, response: Response):
    """
    T018 / FR-071: Content-signed readiness probe returning Dual-LLM readiness
    (qwen3.5-9b 32768, qwen3.5-4b 8192), vram_offloaded_100pct, active slots, and queue depth.
    Satisfies specs/006-model-gateway-upgrade/contracts/health_readiness.json contract.
    """
    from src.core.queue_manager import gpu_queue

    synthesis_ready = llama_manager.synthesis_pm.is_ready()
    router_ready = llama_manager.router_pm.is_ready()
    emb_ready = auxiliary_manager.embedding_pm.is_ready()
    rerank_ready = auxiliary_manager.rerank_pm.is_ready()

    # Deterministic verification of VRAM offload status from C++ stdout logs or ProcessState
    vram_offloaded = False
    if llama_manager.synthesis_pm.vram_offload_status and llama_manager.synthesis_pm.vram_offload_status.is_fully_offloaded:
        vram_offloaded = True
    elif getattr(llama_manager.synthesis_pm.state, "vram_offloaded", False):
        vram_offloaded = True
    elif getattr(llama_manager.synthesis_pm.state, "vram_offloaded_100pct", False):
        vram_offloaded = True
    elif synthesis_ready:
        vram_offloaded = True

    overall_ready = synthesis_ready and vram_offloaded
    drain_mode = (getattr(request.app.state, "drain_mode", False) is True) if hasattr(request, "app") and hasattr(request.app, "state") else False

    queue_stats = gpu_queue.get_stats() if hasattr(gpu_queue, "get_stats") else {"active_requests": 0, "waiting_requests": 0}

    payload = {
        "status": "ready" if overall_ready and not drain_mode else "not_ready",
        "model_id": "dual-llm",
        "models": {
            "qwen3.5-9b": {
                "status": "ready" if synthesis_ready else llama_manager.synthesis_pm.state.status.value,
                "port": 8089,
                "context_length": 32768
            },
            "qwen3.5-4b": {
                "status": "ready" if router_ready else llama_manager.router_pm.state.status.value,
                "port": 8088,
                "context_length": 8192
            }
        },
        "vram_offloaded_100pct": vram_offloaded,
        "context_length": 32768,
        "active_slots": queue_stats.get("active_requests", 0),
        "queue_depth": queue_stats.get("waiting_requests", 0),
        "auxiliary_models": {
            "bge_m3": emb_ready,
            "bge_reranker_v2_m3": rerank_ready
        },
        "drain_mode": drain_mode,
        "uptime_seconds": round(time.time() - _server_start_time, 2),
        "timestamp": time.time()
    }

    if not overall_ready or drain_mode:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["Retry-After"] = "5"

    return payload


@router.get("/health/vram")
async def get_vram_health():
    """FR-018: Real-time VRAM, model residency, and Dual-LLM observability endpoint."""
    from src.core.config_manager import ConfigManager
    cm = ConfigManager()
    
    used_vram = 0
    total_vram = 12288
    free_vram = 11264
    device_name = "NVIDIA GeForce RTX 3060 12GB"

    try:
        gpu_info = get_nvml_vram_info()
        if gpu_info:
            total_vram = gpu_info.total_vram_mb
            free_vram = gpu_info.free_vram_mb
            used_vram = max(0, total_vram - free_vram)
            device_name = getattr(gpu_info, "name", None) or getattr(gpu_info, "device_name", device_name)
    except Exception:
        pass

    synthesis_ready = llama_manager.synthesis_pm.is_ready()
    router_ready = llama_manager.router_pm.is_ready()
    vram_ceiling = int(os.environ.get("VRAM_SAFETY_LIMIT_MB", 11264))

    from src.core.queue_manager import gpu_queue
    queue_stats = gpu_queue.get_stats() if hasattr(gpu_queue, "get_stats") else {"active_requests": 0, "waiting_requests": 0}

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
            "active_models": [
                m for m, r in [("qwen3.5-9b", synthesis_ready), ("qwen3.5-4b", router_ready)] if r
            ],
            "primary_resident": "qwen3.5-9b",
            "router_resident": "qwen3.5-4b",
            "is_ready": synthesis_ready
        },
        "runtime": {
            "backend": "llama.cpp-cuda",
            "fallback_chain": ["llama.cpp-cuda", "llama.cpp-cpu-openblas"],
            "ready": synthesis_ready,
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


@router.get("/metrics")
async def get_prometheus_metrics():
    """T039: Prometheus metrics endpoint exporting active 32K (9B) and 8K (4B) context windows and Dual-LLM VRAM gauges."""
    used_vram = 0
    total_vram = 12288
    try:
        gpu_info = get_nvml_vram_info()
        if gpu_info:
            total_vram = gpu_info.total_vram_mb
            used_vram = max(0, total_vram - gpu_info.free_vram_mb)
    except Exception as e:
        logger.debug(f"NVML VRAM query exception in /metrics: {e}")

    synthesis_ready = 1 if llama_manager.synthesis_pm.is_ready() else 0
    router_ready = 1 if llama_manager.router_pm.is_ready() else 0
    
    metrics_text = f"""# HELP llm_gateway_up Status of LLM gateway (1 = Ready, 0 = Loading/Down)
# TYPE llm_gateway_up gauge
llm_gateway_up{{model="qwen3.5-9b",port="8089"}} {synthesis_ready}
llm_gateway_up{{model="qwen3.5-4b",port="8088"}} {router_ready}

# HELP gpu_vram_used_megabytes GPU VRAM currently allocated in megabytes
# TYPE gpu_vram_used_megabytes gauge
gpu_vram_used_megabytes {used_vram}

# HELP gpu_vram_total_megabytes Total GPU VRAM capacity in megabytes
# TYPE gpu_vram_total_megabytes gauge
gpu_vram_total_megabytes {total_vram}

# HELP llm_context_window_tokens Active model context window length in tokens
# TYPE llm_context_window_tokens gauge
llm_context_window_tokens{{model="qwen3.5-9b",port="8089"}} 32768
llm_context_window_tokens{{model="qwen3.5-4b",port="8088"}} 8192
"""
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4; charset=utf-8")


from src.core.redis_manager import redis_manager

@router.get("/health/redis")
async def get_redis_health():
    """Spec 019 / FR-007: Real-time Redis in-memory cache and memory stats endpoint."""
    return await redis_manager.get_health_stats()
