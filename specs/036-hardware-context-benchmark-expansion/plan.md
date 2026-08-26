# Implementation Plan: 036-hardware-context-benchmark-expansion

**Branch**: `036-hardware-context-benchmark-expansion` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from [`specs/036-hardware-context-benchmark-expansion/spec.md`](./spec.md)

---

## Summary

GTX 1070 8GB 실측 벤치마크 결과를 바탕으로 시스템의 최소 하드웨어 서빙 기준점을 확립합니다:
1. **Tier-1 (실시간 대화 상시 서빙)**: `Qwen 3.5 2B`를 **64K Standard (65,536 tokens) / 128K Ultra (131,072 tokens)** 모드로 상시 VRAM에 고정 상주시켜 0초 로드 대기 시간과 50+ TPS, 0.2s 미만의 TTFT 반응성을 제공합니다.
2. **Tier-2 (고품질 일괄 배치/심층 분석)**: `Qwen 3.5 4B`를 **32K (32,768 tokens)** 모드로 온디맨드 스케줄링하여 뉴스 50건 및 대규모 문맥 심층 분석을 35 TPS로 안정 수행합니다.
3. **고성능 플랫폼 스케일업(Scale-Up)**: 16GB, 24GB, 48GB+ VRAM 환경 감지 시 `model_catalog.json`의 9B, 12B, 27B 모델들을 자동 선별하여 서빙합니다.
4. **TPS SLA 가드**: 실시간 대화 TPS $\ge 30\text{ tokens/s}$, 배치 분석 TPS $\ge 20\text{ tokens/s}$의 서비스 품질 기준점을 보장합니다.

---

## Technical Context

**Language/Version**: Python 3.11, Docker, C++/CUDA Runtime  
**Primary Dependencies**: FastAPI, Uvicorn, llama.cpp (llama-server), Pydantic v2, httpx, NVML / nvidia-smi  
**Storage**: GGUF Model Weights (`/models`), Docker Volume mounts  
**Testing**: pytest, Custom Regression Test Suite (`tests/run_all_regression_tests.py`)  
**Target Platform**: Linux/WSL2 Docker (Host: Windows Desktop / Ubuntu Server, GPU: GTX 1070 8GB ~ A100 80GB)  
**Project Type**: Multi-service microservices (Model Gateway, Oliview Core, Chatbot B, PILOS Analyzer)  
**Performance Goals**: TTFT $\le 300\text{ms}$, Resident 2B TPS $\ge 50\text{ tokens/s}$, 4B Batch TPS $\ge 32\text{ tokens/s}$  
**Constraints**: 8GB VRAM Safe Margin Budget ($\ge 1.0\text{GB}$ Free VRAM), Pascal SM 6.1 FA Fallback  
**Scale/Scope**: 128K Max Context Window, 50-news batch single-pass analysis, 10-turn multi-turn dialogue  

---

## Constitution Check

*GATE: Passed. All architectural principles adhere to Spec-Kit guidelines and empirical measurements.*

| 원칙 | 준수 상태 | 검증 내용 |
| :--- | :---: | :--- |
| **I. Hardware-Aware Scaling** | **PASS** | Pascal SM 6.1 감지 및 VRAM 실측 기반 2B 64K/128K, 4B 32K 안전 상주 보장 |
| **II. Zero False-OOM Guarantee** | **PASS** | Pascal FlashAttention 미지원에 따른 V-Cache 양자화 생략 및 FP16 안전 버퍼 채택 |
| **III. SLA-Driven Multi-Tiering** | **PASS** | 실시간 2B 54 TPS 상시 서빙 + 고품질 4B 35 TPS 온디맨드 스왑 아키텍처 |
| **IV. Scale-Up Portability** | **PASS** | 8GB 최소 사양부터 80GB 고성능 플랫폼까지 9B/12B/27B 자동 프로파일링 |

---

## Project Structure

### Documentation (this feature)

```text
specs/036-hardware-context-benchmark-expansion/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Technical research and benchmark analysis
├── data-model.md        # Entities, schemas, and state transitions
├── contracts/           # API schemas and endpoint contracts
│   └── hardware-capacity-api.json
├── quickstart.md        # Validation guide and verification scenarios
└── checklists/          # Quality checklists
    └── requirements.md
```

### Source Code Changes

```text
model_gateway/
├── config/
│   └── model_catalog.json           # [MODIFY] 2B default_n_ctx=65536, max_n_ctx=131072, 4B default_n_ctx=32768
└── src/
    ├── core/
    │   ├── gpu_detector.py          # [MODIFY] HardwareTierEnum & 9B/12B/27B auto-scaling rules
    │   └── process_manager.py       # [MODIFY] Pascal SM 6.1 FA/KV flag branching & clean swap
    └── api/
        └── routes.py                # [MODIFY] Add /v1/profile and /v1/hardware/capacity endpoints

oliview_core/
└── config.py                        # [MODIFY] Update 3-Tier Harness to 64K_STANDARD & 128K_ULTRA
```

---

## Implementation Phases

### Phase 0: Research & Benchmark Consolidation (Completed)
- [x] Live hardware benchmark execution inside `vllm-serv` container (`benchmark_hardware_limits.py`).
- [x] Verify 2B at 16K, 32K, 64K, 128K (Max 128K, TPS 54 tokens/s, TTFT 190ms).
- [x] Verify 4B at 8K, 16K, 24K, 32K, 48K (Max 48K, TPS 35 tokens/s, TTFT 238ms).
- [x] Measure swap latencies (2B➔4B 37.2s, 4B➔2B 7.4s).

### Phase 1: Model Gateway Configuration & Context Expansion
- [ ] Update `model_gateway/config/model_catalog.json` for `qwen3.5-2b` (`default_n_ctx=65536`, `max_n_ctx=131072`) and `qwen3.5-4b` (`default_n_ctx=32768`).
- [ ] Enhance `model_gateway/src/core/gpu_detector.py` to calculate dynamic scale-up tiers (Baseline 8GB, Mid 16~24GB, High 48GB+).
- [ ] Add `/v1/profile` and `/v1/hardware/capacity` API routes in `model_gateway/src/api/routes.py`.

### Phase 2: Client & Harness Profile Alignment
- [ ] Update `oliview_core/config.py` context harness to support `STANDARD_64K` (65,536 tokens) and `ULTRA_128K` (131,072 tokens).
- [ ] Increase review citation cap to 15 per target and news batch size to 60.

### Phase 3: Verification & Regression Testing
- [ ] Execute Model Gateway unit tests (`pytest model_gateway/tests`).
- [ ] Execute B-Team 7-Suite Regression Tests (`tests/run_all_regression_tests.py`).
- [ ] Verify live inference responsiveness and VRAM telemetry.
