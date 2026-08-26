# Implementation Plan: Dynamic Model Discovery & Hardware-Aware Synchronization

**Branch**: `033-dynamic-model-discovery-sync` | **Date**: 2026-08-26 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/spec.md)

**Input**: Feature specification from `specs/033-dynamic-model-discovery-sync/spec.md`

---

## 1. Summary

하드웨어 VRAM 용량(8GB GTX 1070)에 기반하여 16K 대용량 컨텍스트 윈도우(`n_ctx=16384`)를 보장하는 최적 모델(`qwen3.5-2b`)을 게이트웨이에 상주 서빙하고, 클라이언트(`AiGatewayClient`, `CoreSettings`)가 게이트웨이 `GET /v1/models` 및 `/v1/profile`을 통해 활성 모델명을 **동적으로 탐색(Dynamic Discovery) 및 60초 TTL 캐싱**하여 연동하도록 개선합니다.  
향후 GPU 확장(16GB/24GB) 시 16K를 유지하며 4B/9B로 자동 승격되고, 초장문(32K~64K) 작업 시 소형 모델(2B)로 동적 스케일다운하는 **2차원 VRAM 예산 최적화 아키텍처**를 완성합니다.

---

## 2. Technical Context

**Language/Version**: Python 3.12 (Model Gateway & Chatbot Containers)  
**Primary Dependencies**: FastAPI, Pydantic v2, httpx, llama-server / llama-cpp-python (CUDA 13.0 / FlashAttention), Redis 7  
**Target Platform**: Linux Docker Containers under Windows 11 / WSL2 (NVIDIA GeForce GTX 1070 8GB VRAM)  
**Project Type**: Microservice AI Gateway & Agentic Chatbot Subsystem  
**Performance Goals**: 16K 컨텍스트 상주, LLM 토큰 생성 속도 > 20 tok/s, 동적 모델 탐색 오버헤드 0ms (60s TTL 캐시)  
**Constraints**: 8GB VRAM 한도 내 3개 모델(LLM 16K + BGE-M3 + BGE-Reranker) 100% 무중단 상주, OOM 0건  

---

## 3. Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. 언어 및 커뮤니케이션 정책**: 모든 설계 산출물 및 주석은 한국어로 작성됨.
- [x] **II. TDD 및 테스트 우선주의**: 5대 종합 회귀 테스트 스위트 및 단위 테스트 계약 검증 선행.
- [x] **III. 서비스 모듈화 및 격리**: Gateway와 Client(Chatbot A/B, PILOS) 간 느슨한 결합(Loose Coupling) 및 동적 발견 프로토콜 적용.
- [x] **IV. 관측 가능성 및 구조화된 로깅**: 모델 탐색 및 라우팅 이벤트 구조화 로그(`logger.info`) 기록.
- [x] **V. 단순성 및 점진적 진화 (YAGNI)**: 복잡한 외부 레지스트리 없이 FastAPI 엔드포인트 + 60초 인메모리 TTL 캐시로 가장 단순하고 견고한 설계 채택.

---

## 4. Project Structure & Artifact Map

### Documentation (this feature)

```text
specs/033-dynamic-model-discovery-sync/
├── spec.md                     # Feature Specification (Clarifications & VRAM Matrix)
├── plan.md                     # Implementation Plan (This file)
├── research.md                 # Technical Decisions & 2026 Trends (Phase 0)
├── data-model.md               # Schemas & Cache Data Models (Phase 1)
├── quickstart.md               # Verification & Run Guide (Phase 1)
├── contracts/
│   └── model_discovery_contract.md # API & Interface Contracts (Phase 1)
├── checklists/
│   └── requirements.md         # Specification Quality Checklist
└── tasks.md                    # Actionable Task List (Phase 2, next command)
```

### Source Code Changes

```text
c:/AISERVICE/
├── model_gateway/
│   ├── config/
│   │   ├── server_config.json  # [MODIFY] default_model: qwen3.5-2b, current_n_ctx: 16384
│   │   └── model_config.json   # [MODIFY] current_model: qwen3.5-2b, current_n_ctx: 16384
│   └── src/
│       ├── core/
│       │   └── llama_manager.py # [MODIFY] LOADING state guard & 16K context default
│       └── api/
│           └── routes/
│               └── inference_api.py # [MODIFY] enrich GET /v1/models & transparent 2B mapping
├── bteam/
│   └── oliview_core/
│       ├── config.py           # [MODIFY] auto_discover_model flag & qwen3.5-2b safe default
│       └── client.py           # [MODIFY] implement discover_active_model() with 60s TTL cache
├── .env                        # [MODIFY] SYNTHESIS_LLM_MODEL=qwen3.5-2b
└── docker-compose.yml          # [MODIFY] sync default SYNTHESIS_LLM_MODEL
```

---

## 5. Phase 0 & Phase 1 Execution Status

* **Phase 0 (Research)**: [research.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/research.md) 완결 (2026 최신 트렌드 및 VRAM 토폴로지 매트릭스 확립).
* **Phase 1 (Design & Contracts)**:
  * [data-model.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/data-model.md) 스키마 정의 완결.
  * [contracts/model_discovery_contract.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/contracts/model_discovery_contract.md) API 계약 규격화.
  * [quickstart.md](file:///c:/AISERVICE/specs/033-dynamic-model-discovery-sync/quickstart.md) 실행 검증 가이드 작성.

---

## 6. Next Steps

`/speckit-tasks` 명령어를 실행하여 단위 테스트 작성, 게이트웨이 프로파일 보강, 클라이언트 동적 탐색 캐시 구현, 환경 설정 동기화 태스크(`tasks.md`)를 생성합니다.
