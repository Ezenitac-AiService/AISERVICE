# Implementation Plan: 모델 게이트웨이 LLM/임베딩/리랭커 온로드 및 GPU VRAM 가속 정상화 (Fix Model Gateway LLM Onload & GPU Acceleration)

**Branch**: `044-fix-model-gateway-onload` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/044-fix-model-gateway-onload/spec.md`

## Summary

모델 게이트웨이(`vllm-serv-gateway`)의 런타임 프로브 로직에서 발생한 **자기 자신 포트(8081) 헬스체크 셀프 루프백 오인 버그**와 **Python 모듈 Fallback 시 CUDA 비활성화(`is_cuda_enabled=False`) 하드코딩 버그**를 완전히 해결합니다.
헌법 v1.2.0 원칙 VII(포괄적 무하드코딩 및 인프라 SSOT)에 따라 코드 내 임의 포트/URL 하드코딩을 제거하고, `ENABLE_EXTERNAL_VLLM` 환경 변수를 통한 명시적 제어를 확립하여 기본 기동 시 로컬 임베디드 GPU 가속(`llama.cpp-cuda` @ `-ngl 999`)으로 기본 LLM(`qwen3.5-2b` @ 8089)과 보조 모델(`bge-m3` @ 8090, `bge-reranker-v2-m3` @ 8091)이 실제 GPU VRAM에 100% 온로드되고 503 에러 없이 정상 서비스되도록 합니다.

---

## Technical Context

**Language/Version**: Python 3.12, FastAPI 0.110+, Uvicorn 0.28+

**Primary Dependencies**: `llama_cpp_python` (CUDA 12.x 가속 지원), `httpx`, `pydantic v2`, `pynvml / nvidia-ml-py`, `sse-starlette`

**Storage**: Local Filesystem (GGUF Model Weights in `/app/models`), Redis 7 (캐싱/세션 인프라)

**Testing**: `pytest`, `httpx` 비동기 엔드포인트 E2E 테스트, 소켓 포트 리슨 프로브

**Target Platform**: Linux Container (Ubuntu 24.04 on Docker/WSL2), NVIDIA GeForce GTX 1070 (8GB VRAM, Compute Capability 6.1)

**Project Type**: AI Model Serving Gateway & Proxy Web Service

**Performance Goals**: 기본 모델 기동 60초 이내 VRAM 100% 온로드 완료, 추론 요청 시 503 에러 0건, 최소 보장 TPS SLA 50.0 TPS

**Constraints**: GTX 1070 8GB VRAM 한계 준수 (`VRAM_SAFETY_LIMIT_MB=5000`), 헌법 v1.2.0 원칙 VII(포괄적 무하드코딩) 절대 준수

**Scale/Scope**: 3종 모델 동시 상주 서빙 (Qwen 3.5 2B @ 64K KV, BGE-M3 @ 2K, BGE-Reranker-v2-M3 @ 2K)

---

## Constitution Check

*GATE: Must pass before implementation. All principles evaluated against Constitution v1.2.0.*

| 원칙 | 준수 검토 및 게이트 통과 증적 | 판정 |
| :--- | :--- | :---: |
| **I. 언어 정책** | 모든 문서, 명세서, 계획서, 코드 주석, 사용자 소통을 한국어로 작성 | **PASS** |
| **II. TDD & 계약 검증** | 런타임 프로브 및 프로세스 스폰 계약 테스트 작성 후 구현 및 검증 | **PASS** |
| **III. 서비스 모듈화 & 무결성** | 기존 모델 가중치(GGUF) 및 CUDA 라이브러리 보존, 게이트웨이 내부 로직만 안전 리팩토링 | **PASS** |
| **IV. 관측 가능성 & 로깅** | 포트별 프로세스 PID, 수명주기 전이, 헬스체크 결과를 구조화된 로깅으로 출력 | **PASS** |
| **V. 단순성 (YAGNI)** | 불필요한 복잡성 제거, 기본 설정 시 즉시 로컬 GPU 가속 직결 스폰 | **PASS** |
| **VI. 운영 모드 이원화** | 환경 변수(`.env`) 기반 동적 구성 및 PoC 지연 허용 표준 준수 | **PASS** |
| **VII. 포괄적 무하드코딩 & SSOT** | 코드 내 `8081/health` 하드코딩 완전 제거, `ENABLE_EXTERNAL_VLLM` 명시적 환경 변수 제어 | **PASS** |

---

## Project Structure

### Documentation (this feature)
```text
specs/044-fix-model-gateway-onload/
├── spec.md              # Feature specification
├── plan.md              # This implementation plan
├── research.md          # Technical research & decisions
├── data-model.md        # Data entities & state models
├── contracts/           # API interface contracts
│   └── model-gateway-api-contract.md
├── checklists/          # Quality validation checklists
│   └── requirements.md
└── quickstart.md        # End-to-end validation guide
```

### Source Code Targets
```text
model_gateway/
├── src/
│   ├── config.py                 # 런타임 프로파일 및 Fallback 체인 (하드코딩 제거)
│   ├── core/
│   │   ├── process_manager.py    # 런타임 프로브, CUDA 판정 및 spawn_process 수정
│   │   ├── llama_manager.py      # LlamaManager 생존성 및 상주 상태 검증
│   │   └── auxiliary_manager.py  # 보조 모델(8090/8091) 스폰 및 복구 안정화
│   └── api/
│       ├── server.py             # Lifespan 모델 자동 기동 시퀀스
│       └── routes/
│           ├── inference_api.py  # 추론 프록시 및 백엔드 포워딩
│           └── health_api.py     # 헬스체크 및 준비도 응답
└── tests/
    └── test_model_gateway_onload.py # 신규 회귀 방지 단위/통합 테스트
```

---

## Implementation Phases & Strategy

### Phase 1: 런타임 프로브 및 무하드코딩 리팩토링 (FR-001, FR-006, 헌법 원칙 VII)
1. `model_gateway/src/config.py`:
   - `DEFAULT_FALLBACK_CHAIN`: `ENABLE_EXTERNAL_VLLM=true`가 아닐 때는 기본값에서 `"vllm"`을 제외하고 `["llama.cpp-cuda", "llama.cpp-cpu-openblas"]`로 구성.
   - 외장 vLLM 기본 헬스체크 URL을 게이트웨이 포트(8081)와 충돌하지 않는 전용 분리 포트(예: `http://127.0.0.1:8000/health`)로 분리.
2. `model_gateway/src/core/process_manager.py`:
   - `_runtime_backend_from_profile()`의 `probe("vllm")`에서 게이트웨이 자체 포트(8081) 조회를 금지하고, `ENABLE_EXTERNAL_VLLM` 환경 변수 활성화 시에만 외장 엔드포인트 검사 수행.
   - `spawn_process()` 루프에서 `backend == "vllm"`일 때도 셀프 포트 8081 헬스체크를 제거하고 실제 외장 vLLM 헬스체크를 수행하도록 수정.

### Phase 2: Python 모듈 Fallback의 CUDA VRAM 가속 복구 (FR-002)
1. `model_gateway/src/core/process_manager.py`:
   - `verify_and_build_llama_server()`에서 `PYTHON_MODULE_FALLBACK` 생성 시 `is_cuda_enabled`를 `False`로 고정하지 않고, `llama_cpp.llama_supports_gpu_offload()`가 `True`이면 `is_cuda_enabled=True`로 동적 설정.
   - `build_server_command()`에서 `is_cuda_enabled=True`일 때 `--n_gpu_layers 999`가 주입되어 모델 가중치가 GPU VRAM으로 100% 온로드되도록 보장.

### Phase 3: 프로세스 생존성 및 실시간 헬스 바인딩 (FR-003, FR-004, FR-005)
1. `model_gateway/src/core/process_manager.py`:
   - `spawn_process()`에서 실제 OS 프로세스를 생성하고 `self.process.pid`가 양의 정수로 획득되며, 포트 헬스체크(`poll_server_health`)가 통과했을 때만 `READY` 상태로 전이.
   - `is_ready()` 판단 시 `self.state.status == READY and self.process is not None and self.process.returncode is None` 조건을 엄격히 적용하여 프로세스 미기동 상태에서 가짜 READY가 되는 현상을 원천 차단.
2. `model_gateway/src/core/llama_manager.py` & `auxiliary_manager.py`:
   - `ensure_default_model_resident()` 및 `ensure_embedding_resident()`, `ensure_rerank_resident()`가 실제 프로세스 생존 여부를 확인하고 필요 시 즉시 프로세스를 스폰하도록 보장.

### Phase 4: 테스트 작성 및 전수 E2E 검증 (FR-007, SC-001~SC-005)
1. `tests/test_model_gateway_onload.py` 작성:
   - 런타임 프로브가 8081 포트를 vLLM으로 오인하지 않는지 검증.
   - `PYTHON_MODULE_FALLBACK`에서 CUDA 가속 플래그(`is_cuda_enabled=True`, `-ngl 999`) 주입 검증.
   - 가짜 `READY (pid: None)` 상태가 발생하지 않는지 검증.
2. 컨테이너 내부 3종 모델(LLM 8089, 임베딩 8090, 리랭커 8091) 동시 기동 및 E2E API 호출 실측 검증.

---

## Verification Plan

### Automated Unit & Integration Tests
- `pytest tests/test_model_gateway_onload.py`: 신규 작성된 런타임 백엔드 및 프로세스 매니저 단위 테스트 전수 통과.
- `pytest tests/test_migration_convergence.py`: 기존 마이그레이션 팩 수렴 테스트 회귀 검증 통과.

### Live Container E2E Verification
- 포트 8081, 8089, 8090, 8091 전체 `OPEN` 확인.
- `GET /health/readiness` -> HTTP 200 `{"status": "ready"}` 확인.
- `POST /v1/chat/completions` -> HTTP 200 LLM 답변 스트리밍 수신 확인.
- `POST /v1/embeddings` -> HTTP 200 벡터 생성 확인.
- `POST /v1/rerank` -> HTTP 200 연관도 점수 확인.
- 챗봇 프론트엔드/백엔드와의 연동 질의 시 503 에러 0건 확인.
