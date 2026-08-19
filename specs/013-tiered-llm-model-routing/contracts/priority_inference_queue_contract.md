# API Contract: Priority Inference Queue & Observability

**Contract Version**: 1.0.0  
**Feature**: `013-tiered-llm-model-routing`  
**Endpoints**:
- `GET /health/vram` (VRAM 및 큐 관측 모니터링)
- `GET /v1/models` (동적 모델 카탈로그)

---

## 1. `GET /health/vram` (실시간 상태 모니터링)

게이트웨이와 GPU VRAM, 상주 모델, 대기 큐 상태를 반환합니다.

### 1.1 응답 사양 (HTTP 200 OK)
```json
{
  "status": "healthy",
  "timestamp": 1724050100,
  "gpu": {
    "device_name": "NVIDIA GeForce GTX 1070",
    "total_vram_mb": 8192,
    "used_vram_mb": 4720,
    "free_vram_mb": 3472,
    "vram_limit_ceiling_mb": 5000,
    "is_within_safety_margin": true
  },
  "models": {
    "active_models": ["qwen3.5-2b", "qwen3.5-4b"],
    "primary_resident": "qwen3.5-2b",
    "on_demand_resident": "qwen3.5-4b",
    "idle_seconds_remaining": 420
  },
  "auxiliary_services": {
    "embedding_bge_m3": {
      "port": 8090,
      "device": "CPU",
      "vram_mb": 0,
      "status": "READY"
    },
    "reranker_bge_m3": {
      "port": 8091,
      "device": "CPU",
      "vram_mb": 0,
      "status": "READY"
    }
  },
  "scheduler_queue": {
    "high_priority_waiting": 0,
    "low_priority_waiting": 1,
    "currently_executing": {
      "model": "qwen3.5-2b",
      "priority": "low",
      "task": "A-Team Market Commentary Batch"
    }
  }
}
```

---

## 2. 우선순위 스케줄링 규칙 계약 (Queue Behavior Contract)

1. **선점 규칙 (Preemption Rule)**:
   - `priority: "high"` (웹 챗봇, 실시간 사용자 질의) 요청이 인입되면, 대기 중인 `priority: "low"` (10분 주기 정기 리포트 배치) 요청보다 **항상 먼저 `_llm_inference_lock`을 획득**한다.
2. **배치 청크 분할 (Chunking)**:
   - A팀 정기 배치는 10개 종목을 1개의 거대 트랜잭션으로 묶지 않고, **1개 종목 단위(1~2초)로 락을 해제/재획득**하여 사용자 요청이 최대 2초 이내에 끼어들 수 있도록 보장한다.
