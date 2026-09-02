# Feature Specification: 모델 게이트웨이 LLM/임베딩/리랭커 온로드 및 GPU VRAM 가속 정상화 (Fix Model Gateway LLM Onload & GPU Acceleration)

**Feature Branch**: `044-fix-model-gateway-onload`

**Created**: 2026-09-02

**Status**: Clarified (Ready for Planning)

**Input**: User description: "모델 게이트웨이 컨테이너가 llm 모델 온로드 안한것 같은데? 지금까지 문제가 없었다가 생긴 원인 분석 및 스펙 명확화"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 기본 초고속 LLM 모델 VRAM 온로드 및 정상 추론 서빙 (Priority: P1)

사용자(챗봇 사용자 또는 프론트엔드/백엔드 클라이언트)가 올리뷰 챗봇 A, B 및 필로스 챗봇을 통해 질의를 입력했을 때, 모델 게이트웨이가 기본 초고속 LLM 모델(`qwen3.5-2b`)을 GPU VRAM에 완전히 온로드한 상태에서 즉시 503 에러 없이 정상적인 AI 생성 답변(스트리밍/일반 응답)을 제공받는다.

**Why this priority**: 모델 게이트웨이의 핵심 목적은 LLM 추론 서빙이며, 현재 LLM 서브프로세스가 뜨지 않아 모든 챗봇 서비스에서 503 Service Unavailable 장애가 발생하고 있으므로 최우선 해결 과제이다.

**Independent Test**: 모델 게이트웨이 기동 후 `/v1/chat/completions` 엔드포인트로 테스트 프롬프트를 전송하여 HTTP 200 응답과 생성된 텍스트가 정상 수신되는지 독립적으로 검증한다.

**Acceptance Scenarios**:

1. **Given** 모델 게이트웨이 컨테이너가 기동되었을 때, **When** 백그라운드 모델 로딩 시퀀스가 완료되면, **Then** `qwen3.5-2b` 모델 프로세스가 포트 8089에서 실행 중(PID 할당)이어야 하고 `/health/readiness`가 실제 프로세스 생존에 기반하여 200 OK를 반환해야 한다.
2. **Given** 기본 모델이 로드된 상태에서, **When** 클라이언트가 `POST /v1/chat/completions` 요청을 전송하면, **Then** 503 에러 없이 200 OK와 함께 완성된 LLM 텍스트 응답이 반환되어야 한다.

---

### User Story 2 - 임베딩 및 리랭커 보조 서빙 프로세스 정상 기동 및 검색 서빙 (Priority: P2)

RAG 및 벡터 검색 파이프라인(챗봇 B, 필로스 등)이 문서 검색, 임베딩 생성, 리랭킹을 요청했을 때, 보조 모델 관리자가 BGE-M3(임베딩, 포트 8090) 및 BGE-Reranker-v2-M3(리랭커, 포트 8091) 프로세스를 정상 스폰하여 검색/재순위화 요청을 성공적으로 처리한다.

**Why this priority**: RAG 기반 화장품 추천 및 문서 기반 답변 생성에 임베딩/리랭커가 필수적이므로, LLM 서빙과 함께 즉시 가동되어야 한다.

**Independent Test**: `/v1/embeddings` 및 `/v1/rerank` 엔드포인트에 텍스트 및 문서 목록을 전송하여 각각 유효한 임베딩 벡터와 연관도 점수 목록(HTTP 200)을 수신하는지 검증한다.

**Acceptance Scenarios**:

1. **Given** 모델 게이트웨이가 기동되었을 때, **When** 보조 모델 매니저가 기동을 완료하면, **Then** 포트 8090(임베딩)과 포트 8091(리랭커)에 각각 독립된 서브프로세스가 실행 상태여야 한다.
2. **Given** 보조 모델 프로세스가 활성화된 상태에서, **When** RAG 서비스가 임베딩 또는 리랭킹을 요청하면, **Then** 타임아웃이나 연결 실패(ConnectError) 없이 200 OK 결과를 반환해야 한다.

---

### User Story 3 - 런타임 백엔드 프로브 및 Fallback의 결함 없는 안전 동작 (Priority: P3)

시스템 운영자가 컨테이너를 재시작하거나 다양한 런타임 환경(외장 vLLM, 독립 llama-server 바이너리, 내장 python llama_cpp 모듈 등)에서 게이트웨이를 실행할 때, 게이트웨이가 자기 자신의 포트(8081)를 외장 런타임으로 착각하지 않고, 명시적인 외장 vLLM 활성화 플래그(`ENABLE_EXTERNAL_VLLM=true`)가 없을 때는 즉시 로컬 임베디드 GPU 가속 서빙으로 진입하여 결함 없이 실행된다.

**Why this priority**: 잘못된 프로브 URL 및 셀프 루프백 오인으로 인해 가짜 READY 상태가 되는 버그를 원천 차단하여 인프라 마이그레이션 및 재기동 시의 시스템 견고성을 보장한다.

**Independent Test**: 외장 vLLM이 없는 기본 컨테이너 환경에서 프로브가 외장 vLLM을 성공으로 잘못 판정하지 않고 올바르게 로컬 `llama_cpp-cuda` 백엔드로 직결하여 실제 서브프로세스를 기동하는지 확인한다.

**Acceptance Scenarios**:

1. **Given** 기본 설정(`ENABLE_EXTERNAL_VLLM=false` 또는 미설정)일 때, **When** 게이트웨이가 기동되면, **Then** 자기 자신 포트(8081)에 대한 vLLM 프로브를 시도하지 않고 즉시 `llama.cpp-cuda` 백엔드를 통해 로컬 서브프로세스를 스폰해야 한다.
2. **Given** `ENABLE_EXTERNAL_VLLM=true` 및 분리된 외장 포트(`VLLM_PORT` 또는 `VLLM_HEALTH_URL`, 예: `http://127.0.0.1:8000/health`)가 설정된 경우, **When** 외장 vLLM이 정상 응답(200 OK)하면, **Then** 외장 vLLM을 1순위 런타임으로 활성화해야 한다.
3. **Given** C++ 바이너리 없이 Python llama_cpp 모듈로 실행될 때, **When** GPU 가속 지원 환경이면, **Then** `is_cuda_enabled`가 True로 설정되어 GPU VRAM 레이어 오프로드(`--n_gpu_layers 999`) 인자가 적용되어야 한다.

---

### Edge Cases

- **GPU VRAM 부족 또는 드라이버 미인식 상황**: NVIDIA 드라이버나 CUDA 환경에 문제가 발생할 경우 시스템은 무한 대기나 가짜 READY 대신 명확한 에러 상태(`ERROR`)를 기록하고 CPU fallback 체인을 통해 최소한의 서빙 가능성을 확보해야 한다.
- **프로세스 비정상 종료 (Crash) 발생 시**: 백엔드 프로세스가 예기치 않게 종료된 경우, 게이트웨이는 `is_ready() == False`로 즉시 상태를 갱신하고 자동 복구(Auto Recovery) 재기동을 시도해야 한다.
- **연속 요청 유입 중 프로세스 미준비 상태**: 모델 로딩 또는 준비 중 들어오는 추론 요청에 대해 500 내부 서버 오류가 아닌 명확한 `503 Service Unavailable` 및 `Retry-After` 헤더를 반환하고, 준비 완료 즉시 200으로 전환되어야 한다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 모델 게이트웨이 런타임 백엔드 프로브(`_runtime_backend_from_profile` 및 `spawn_process`) 시 게이트웨이 자체 포트(`8081`)를 vLLM 헬스체크 URL로 사용하지 않아야 하며, `ENABLE_EXTERNAL_VLLM=true` 플래그가 켜져 있고 전용 분리 포트(예: 8000)가 지정된 경우에만 외장 vLLM 프로브를 실행해야 한다. (기본값: 로컬 `llama.cpp-cuda` 우선 기동)
- **FR-002**: 시스템은 `PYTHON_MODULE_FALLBACK` 환경에서도 `llama_cpp.llama_supports_gpu_offload()` 또는 CUDA 환경 감지 결과에 따라 `is_cuda_enabled`를 동적으로 결정하여, GPU VRAM 오프로드(`--n_gpu_layers 999`)가 정상 작동하도록 구성해야 한다.
- **FR-003**: 시스템은 기본 LLM 모델(`qwen3.5-2b`) 로드 시 실제 OS 서브프로세스를 생성하고 유효한 `PID`를 획득해야 하며, 백엔드 포트(8089) 헬스체크가 검증되었을 때만 `ProcessStatusEnum.READY`로 전이해야 한다. (PID가 None인 상태에서 가짜 READY 전이 금지)
- **FR-004**: 시스템은 보조 모델 매니저(`AuxiliaryModelManager`)를 통해 임베딩(`bge-m3` @ 8090) 및 리랭커(`bge-reranker-v2-m3` @ 8091) 프로세스를 각각 독립 스폰하고 실제 헬스체크 성공 여부를 확인해야 한다.
- **FR-005**: 시스템은 프로세스가 실제로 떠 있지 않거나 소켓이 닫혀 있는 경우 `is_ready()`를 `False`로 판정하여, 프록시 포워딩 에러 발생 시 자동 로드 및 복구 루틴이 정상 격발되도록 보장해야 한다.
- **FR-006**: 시스템은 헌법 v1.2.0 원칙 VII(포괄적 무하드코딩 및 인프라 SSOT)을 준수하여, 모든 포트 번호, 백엔드 URL, 런타임 플래그에 대한 임의 하드코딩을 제거하고 환경 변수(`.env`) 및 `ConfigManager`로 단일화해야 한다.
- **FR-007**: 시스템은 기본 LLM 준비 완료 시 `/health/readiness`에서 200 OK를 반환하며, 보조 모델(임베딩/리랭커)의 상태는 `/health` 및 `/v1/models`를 통해 독립 관측 및 장애 격리(Fault Isolation)를 유지해야 한다.

### Key Entities *(include if feature involves data)*

- **ProcessState**: 서빙 프로세스의 수명 주기 상태(`status`), 모델 식별자(`model_id`), 바인딩 포트(`port`), 운영체제 프로세스 ID(`pid`), 에러 메시지(`error_message`), VRAM 오프로드 완납 여부(`vram_offloaded_100pct`)를 보관하는 불변 데이터 모델.
- **LlamaServerBinaryInfo**: 실행할 바이너리 경로(`binary_path`), CUDA 가속 활성화 여부(`is_cuda_enabled`), 바이너리 취득 출처(`build_source`), 런타임 백엔드(`runtime_backend`) 정보를 관리하는 데이터 모델.
- **RuntimeProfile**: 하드웨어 가용성 및 VRAM 예산, fallback 순서(`runtime_fallback_chain`), 백엔드 상태를 정의하는 런타임 구성 엔티티.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 모델 게이트웨이 기동 후 60초 이내에 기본 초고속 모델(`qwen3.5-2b`)이 GPU VRAM에 온로드되고 포트 8089 프로세스가 활성화되어 PID가 정상 등록된다.
- **SC-002**: 챗봇 추론 요청(`POST /v1/chat/completions`) 발생 시 503 에러 없이 100% 성공(HTTP 200) 응답을 반환한다.
- **SC-003**: 임베딩(포트 8090) 및 리랭커(포트 8091) 프로세스가 정상 기동되어 `/v1/embeddings` 및 `/v1/rerank` 호출이 정상(HTTP 200) 처리된다.
- **SC-004**: 프로세스 상태가 `READY`일 때 `PID`가 유효한 양의 정수값을 가지며, 가짜 `READY (pid: None)` 상태가 발생하지 않는다.
- **SC-005**: 헌법 v1.2.0 원칙 VII에 따라 코드 내 임의 포트/URL 하드코딩이 0건으로 검증된다.

## Assumptions & Clarified Decisions

- **컨텍스트 및 VRAM 예산 (Clarified)**: 기존 정책(Spec 036)에 따라 2B 기본 모델은 64K(65,536) 표준 컨텍스트를 유지하며, `DynamicHardwareProfile`에 의해 GTX 1070(8GB VRAM)의 실가용 용량 내에서 안전하게 서빙된다.
- **서비스 준비도 및 장애 격리 (Clarified)**: `/health/readiness`는 기존 정책대로 기본 LLM 프로세스 생존 및 포트 8089 헬스체크 통과 시 200 OK를 반환하며, 보조 모델(임베딩/리랭커)은 독립 장애 격리 및 온디맨드 자동 복구를 유지한다.
- **런타임 백엔드 활성화 규칙 (Clarified)**: `ENABLE_EXTERNAL_VLLM=false`가 기본값이며, 외장 vLLM이 명시적으로 켜지지 않은 경우 게이트웨이 기동 즉시 로컬 임베디드 `llama.cpp-cuda` (GPU 가속 @ `-ngl 999`)로 직결 스폰된다.
- **하드웨어 환경**: NVIDIA GeForce GTX 1070 (8GB VRAM) 및 CUDA 12.x / Compute Capability 6.1 지원 환경을 기본 GPU 가속 타겟으로 한다.
- **로컬 모델 가중치**: `models/qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf`, `models/bge-m3/bge-m3-q8_0.gguf`, `models/bge-reranker-v2-m3/bge-reranker-v2-m3-q8_0.gguf` 파일이 로컬 볼륨에 정상 배치되어 있다.
- **서빙 바이너리/모듈**: 컨테이너 내부에 `llama_cpp_python` (CUDA 가속 지원) 모듈이 정상 설치되어 있어 `python3 -m llama_cpp.server`를 통한 GPU 가속 서빙이 가능하다.
