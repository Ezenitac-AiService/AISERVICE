# Feature Specification: Dynamic Model Discovery & Hardware-Aware Gateway Synchronization

**Feature Branch**: `033-dynamic-model-discovery-sync`  
**Created**: 2026-08-26  
**Status**: Draft  
**Input**: User description: "2b 모델 서비스와 16k 컨텍스트 윈도우 크기는 하드코딩이 아닌, gpu vram 크기로 판단한 결과이고, 그것을 설정값으로 저장해서 나머지 컨테이너와 워커, 서비스들이 동적으로 받아들여서 동작해야 해, 하드웨어 교체로 gpu vram이 커지면, 4b를 16k, 9b를 16k 등으로 최소 16k 컨텍스트 윈도우 크기를 유지하면서 oom이 발생하지 않는 기준점으로 모델을 선택하고 서비스 하도록, vram이 커지면, 작은 모델은 옵션으로 스위칭 될수도 있고, 작은 모델이 필요한 상황은 더 큰 컨텍스트 윈도우 크기가 필요할 경우야. 타당성 검토해주고, 2026년 8월 기준 최신 트랜드를 리서치해서 검토, 검증해줘"

---

## 1. 개요 및 배경 (Context & Problem Statement)

## Clarifications

### Session 2026-08-26
- **Q1:** 2B 모델로 4B 수준의 RAG 심층 합성을 커버하기 위해 컨텍스트 윈도우 크기 축소를 방지하고 대용량 컨텍스트를 보장할 때, 기본 목표 컨텍스트 윈도우 크기는 몇으로 설정해야 합니까?  
  **A1:** **16K (16,384 tokens) 상주 보장** (2B 모델이 4B 업무를 커버하도록 컨텍스트 윈도우 임의 축소를 금지하고 대용량 RAG 문맥을 완전 수용).
- **Q2:** GPU VRAM 확장에 따른 모델 자동 선택 및 초장문 컨텍스트(32K~64K) 요구 시 소형 모델(2B) 동적 스위칭 아키텍처의 원칙과 기준은 무엇입니까?  
  **A2:** **하드웨어 VRAM 예산 기반 2차원 동적 최적화 (2D Dynamic Budget Balancing)**:
  1. **최소 컨텍스트 제약 조건**: 모든 기본 LLM 서비스는 **최소 16K (`min_n_ctx=16384`) 컨텍스트 윈도우를 필수로 보장**한다.
  2. **VRAM 용량별 기본 모델 자동 선정**:
     - $\text{VRAM Total} \ge \text{Model Weights} + \text{KV Cache}(16\text{K}) + \text{Aux Models}(1.6\text{GB}) + \text{OS Buffer}$ 공식을 통해 OOM 없이 100% VRAM 상주 가능한 **최대 파라미터 모델**을 기본 서빙 모델로 자동 결정:
       - **8GB GPU (GTX 1070)**: `qwen3.5-2b` (16K ctx, VRAM 점유 ~3.3GB + OS 3.7GB = 7.0GB)
       - **16GB GPU (RTX 4080 / T4)**: `qwen3.5-4b` (16K ctx, VRAM 점유 ~4.8GB)
       - **24GB+ GPU (RTX 3090 / 4090)**: `qwen3.5-9b` (16K ctx, VRAM 점유 ~7.8GB)
  3. **초장문 컨텍스트 스케일다운 (Context-Driven Downscaling)**:
     - 고용량 VRAM 환경에서 기본 모델이 4B/9B로 승격되더라도, **초대형 문서(32K~64K+) 분석 작업**이 요청될 경우 가벼운 2B 모델로 동적 스위칭하여 VRAM OOM 없이 초장문 윈도우를 제공한다.
  4. **동적 전파(Dynamic Discovery & Propagation)**:
     - 모델 게이트웨이가 하드웨어 VRAM 및 설정을 기반으로 최적 모델 프로파일을 계산하여 노출(`GET /v1/models` 및 `/v1/profile`)하고, 전사 다운스트림 서비스(Chatbot A/B, PILOS, Worker)는 이를 동적으로 읽어 동작한다.

---

### 1.1 현상 및 배경 분석 (Background Analysis)
1. **과거 정적 계층형 라우팅의 한계**:
   - 과거에는 코드 및 환경변수(`.env`)에 `SYNTHESIS_LLM_MODEL=qwen3.5-4b`와 같이 고정 문자열이 기재되어, 하드웨어 사양이 바뀌거나 8GB 환경으로 다운스케일될 때 프로세스 킬/OOM 충돌이 발생했습니다.
2. **2026 최신 업계 동향 (Industry Trends & Feasibility)**:
   - 2026년 기준 LLM 서빙 프레임워크(vLLM PagedAttention, llama.cpp FlashAttention-3 및 Q8 KV Cache)는 **하드웨어 제약 기반 동적 프로파일링(Hardware-Aware Dynamic Profiling)**과 **라우터 계층 기반 모델/컨텍스트 티어링(Compound AI Systems)**을 표준 아키텍처로 채택하고 있습니다.
   - 파라미터 용량(Parameter Quality)과 컨텍스트 길이(Context Capacity)를 고정하지 않고, 단일 VRAM 예산 내에서 **작업의 성격(장문 RAG vs 고난도 추론)에 따라 동적으로 트레이드오프**하는 설계는 2026년 업계 최고 수준의 효율적 패턴입니다.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 클라이언트의 게이트웨이 활성 모델 동적 탐색 (Priority: P1)

챗봇 클라이언트 서비스(A팀/B팀) 및 워커는 기동 시 및 런타임에 모델 게이트웨이의 활성 모델 목록을 조회하여, 게이트웨이가 하드웨어 VRAM 기준으로 서빙 중인 최적의 기본 LLM 모델명을 동적으로 획득하여 사용합니다.

**Why this priority**: 하드웨어 교체나 게이트웨이 설정 변경 시 다운스트림 코드/환경변수를 일일이 수정하지 않고 전사 서비스가 자동 동기화되도록 보장합니다.

**Independent Test**: 클라이언트 환경변수를 지정하지 않더라도, 게이트웨이 `GET /v1/models`에 등록된 활성 모델(`qwen3.5-2b`, 16K ctx)로 자동 감지되어 RAG 합성이 정상 수행되는지 검증합니다.

**Acceptance Scenarios**:
1. **Given** 게이트웨이가 8GB VRAM에 맞추어 `qwen3.5-2b (16K ctx)`를 상주 서빙 중일 때, **When** 챗봇 클라이언트가 초기화되면, **Then** 클라이언트는 게이트웨이로부터 활성 모델명(`qwen3.5-2b`)을 획득하여 RAG 생성에 사용한다.
2. **Given** 게이트웨이 통신이 일시 지연될 때, **When** 모델 조회가 실패하면, **Then** 클라이언트는 안전 기본값(`qwen3.5-2b`)으로 자동 폴백한다.

---

### User Story 2 - GPU VRAM 확장 시 고사양 모델 자동 승격 (Priority: P2)

운영자가 GPU 하드웨어를 16GB(RTX 4080) 또는 24GB(RTX 4090)로 교체하거나 설정을 변경하면, 게이트웨이는 16K 컨텍스트를 유지하면서 4B 또는 9B 모델을 기본 상주 모델로 자동 승격하고 클라이언트가 이를 동적으로 반영합니다.

**Why this priority**: 하드웨어 업그레이드 시 시스템 재설계 없이 즉시 고품질 모델로 스케일업할 수 있습니다.

**Independent Test**: 게이트웨이 `server_config.json`의 기본 모델을 `qwen3.5-4b`로 변경하고 재기동했을 때, 클라이언트가 60초 이내에 4B 모델을 자동 인식하고 호출하는지 확인합니다.

**Acceptance Scenarios**:
1. **Given** 16GB VRAM 환경에서 `default_model`이 `qwen3.5-4b`로 지정되었을 때, **When** 클라이언트가 RAG 질의를 전송하면, **Then** 클라이언트는 `qwen3.5-4b`로 요청을 전송하고 정상 응답을 수신한다.

---

### User Story 3 - 초장문 컨텍스트(32K~64K) 요구 시 소형 모델 동적 스위칭 (Priority: P3)

대용량 문서 분석이나 장기 대화 히스토리 등 16K를 초과하는 32K~64K 초장문 컨텍스트 처리가 요구되는 특수 작업 시, 시스템은 경량 2B 모델을 선택적으로 호출하여 VRAM OOM 없이 초장문 윈도우를 안전하게 처리합니다.

**Why this priority**: 고용량 VRAM 환경에서도 초대형 컨텍스트 요구 시 OOM 크래시를 방지하고 처리량을 극대화합니다.

**Independent Test**: 32K 토큰 이상의 컨텍스트를 주입하는 특수 배치/분석 작업 요청 시, 2B 모델로 동적 라우팅되어 OOM 없이 토큰 생성이 완결되는지 검증합니다.

**Acceptance Scenarios**:
1. **Given** 고사양 GPU 환경에서 4B가 기본 서비스 중일 때, **When** 클라이언트가 32K 초장문 컨텍스트 처리를 요청하면, **Then** 시스템은 경량 `qwen3.5-2b`로 라우팅하여 OOM 없이 처리를 완결한다.

---

### User Story 4 - 레거시/비상주 모델 요청에 대한 게이트웨이 투명 매핑 (Priority: P4)

외부 클라이언트나 테스트 스크립트가 `qwen3.5-4b` 등 현재 비상주 모델명을 요청하더라도, 게이트웨이가 프로세스 재시작이나 500 에러 없이 현재 상주 모델로 즉시 투명 라우팅합니다.

**Why this priority**: 구버전 클라이언트와의 100% 하위 호환성을 유지하고 무중단 서빙을 보장합니다.

**Independent Test**: `model: "qwen3.5-4b"` 페이로드 호출 시 500 에러 없이 200 OK와 스트리밍 응답이 반환되는지 검증합니다.

---

## 3. 요구사항 (Requirements) *(mandatory)*

### Functional Requirements

- **FR-001**: 모델 게이트웨이는 하드웨어 VRAM 용량 및 안전 버퍼를 기반으로 16K 컨텍스트를 보장하는 최적 상주 모델(`qwen3.5-2b` on 8GB, `qwen3.5-4b` on 16GB, `qwen3.5-9b` on 24GB)을 결정하고 이를 설정 파일([server_config.json](file:///c:/AISERVICE/model_gateway/config/server_config.json)) 및 상태로 관리해야 한다.
- **FR-002**: 게이트웨이 `GET /v1/models` 및 `GET /v1/profile` API는 현재 상주 중인 활성 모델명, 지원 컨텍스트 윈도우 크기(`16384`), 활성 플래그(`is_active: true`)를 JSON으로 제공해야 한다.
- **FR-003**: 클라이언트 라이브러리(`AiGatewayClient`)는 기동 시 및 주기적(TTL 60초 캐싱)으로 게이트웨이의 활성 모델을 동적으로 탐색하는 `discover_active_model()` 메서드를 제공해야 한다.
- **FR-004**: 클라이언트 설정(`CoreSettings`)은 환경변수가 비어있거나 불일치할 경우 동적으로 감지된 활성 모델명을 기본 합성 모델(`synthesis_llm_model`)로 자동 채택해야 한다.
- **FR-005**: 게이트웨이의 `reverse_proxy`는 `SINGLE_MODEL_MODE=true` 상태에서 비상주 모델 요청이 유입될 경우, 프로세스 킬/스와핑 없이 상주 모델로 투명하게 재매핑하여 서빙해야 한다.
- **FR-006**: 초장문 컨텍스트(32K~64K) 요청이 발생할 경우, 모델 매니저는 2B 등 경량 모델을 선택적으로 바인딩하여 VRAM 한도 내에서 안전하게 처리해야 한다.
- **FR-007**: 2B 모델이 4B 업무를 온전히 커버할 수 있도록 기본 컨텍스트 윈도우 크기(`current_n_ctx`)를 **16K (16,384 tokens)**로 상주 보장해야 하며 임의 축소를 엄격히 금지한다.
- **FR-008**: 루트 `.env` 및 `docker-compose.yml`의 `SYNTHESIS_LLM_MODEL` 기본값을 `qwen3.5-2b`로 정합성 있게 통일한다.

---

## 4. Success Criteria *(mandatory)*

1. **하드웨어 최적화 동적 연동**: 게이트웨이의 서빙 모델/컨텍스트 변경 시, 클라이언트 코드 수정이나 재배포 없이 60초 이내에 클라이언트가 새 모델명을 동적으로 반영 (반영 성공률 100%).
2. **16K 대용량 컨텍스트 안정 상주**: `qwen3.5-2b` 모델이 `n_ctx=16384`로 상주하여 10~20개 제품 리뷰 문맥을 완벽히 수용하고 OOM 없이 실시간 토큰 생성(20+ tok/s) 달성.
3. **설정 불일치 크래시 0건**: 클라이언트의 모델명 불일치로 인한 불필요한 프로세스 킬, 핫스왑 OOM, 500 에러 발생 건수 **0건**.
4. **회귀 테스트 무결점**: 전사 5대 종합 회귀 테스트 스위트 100% 통과 유지.

---

## 5. Key Entities & VRAM Topology Matrix

### VRAM & Model Topology (2026 Architecture)

| GPU VRAM 용량 | 기본 서빙 모델 | 필수 컨텍스트 | VRAM 소모 (모델+16K KV+Aux) | 초장문 컨텍스트 확장 옵션 (32K~64K) |
| :--- | :--- | :---: | :--- | :--- |
| **8GB (GTX 1070)** *(현재)* | **`qwen3.5-2b`** | **16K (16,384)** | **~3.3GB** (+ OS 3.7GB = 7.0GB) | 2B 모델로 32K까지 확장 가능 (~3.6GB) |
| **16GB (RTX 4080)** | **`qwen3.5-4b`** | **16K (16,384)** | **~4.8GB** (여유 11.2GB) | 초장문 64K 필요 시 2B 모델로 동적 스케일다운 |
| **24GB (RTX 4090)** | **`qwen3.5-9b`** | **16K (16,384)** | **~7.8GB** (여유 16.2GB) | 초장문 128K 필요 시 2B/4B 모델로 동적 스케일다운 |
