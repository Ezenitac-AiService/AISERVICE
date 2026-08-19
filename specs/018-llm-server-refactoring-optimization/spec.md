# Feature Specification: 018-llm-server-refactoring-optimization (2026 최신 트렌드 기반 LLM 서빙 게이트웨이 현대화 및 추론 성능 최적화)

**Feature Branch**: `018-llm-server-refactoring-optimization`

**Created**: 2026-08-19

**Status**: Draft (Ready for Validation & Clarification)

**Input**: User description: "llm 서버 리펙토링과 최적화를 위한 리서치를 진행해줘 2026년 8월 기준 최신 트랜드, 기술, 방법론등 정보를 조사해서 스펙을 작성해줘"

---

## 1. 개요 및 배경 (Overview & 2026 Technical Landscape)

### 📌 2026년 8월 기준 LLM 추론 서빙 최신 기술 트렌드 및 당면 과제
2026년 현재 생성형 AI 서빙 생태계는 단순한 모델 로딩을 넘어 **고밀도 양자화(Q4_K_M, Q5_K_M, FP8), 프리픽스 캐싱(Prefix Caching / RadixAttention), 청크 프리필(Chunked Prefill), 추측 디코딩(Speculative Decoding), 구조화된 제약 디코딩(Constrained Decoding / BNF Grammar)**을 결합한 복합 추론 최적화 아키텍처로 진화했습니다.

현재 AISERVICE의 모델 서빙 게이트웨이(`model_gateway / vllm-serv-gateway`)는 Qwen3.5 계열(2B Fast/Report, 4B Synthesis/Chat), BGE-M3 임베딩(Port 8090), BGE-Reranker-v2-m3(Port 8091)을 통합 서빙하며 안정적으로 가동 중이나, 다음과 같은 아키텍처적 부채와 성능 최적화 여지가 존재합니다:

1. **RAG 공통 컨텍스트 재계산 오버헤드**:
   - 시스템 프롬프트 및 참조 리뷰/수급 지표 데이터가 매 쿼리마다 반복 입력되지만, 프리픽스 캐시(`Prompt Cache / Prefix Caching`)가 비활성화되어 TTFT(Time-To-First-Token)가 불필요하게 증가함.
2. **긴 프롬프트 입력 시 프리필 지연 스파이크**:
   - 대량 리뷰(2000+ 토큰) 유입 시 청크 프리필(Chunked Prefill)이 미적용되어 디코딩 스트림과 프리필 단계의 인터리빙이 원활하지 못함.
3. **서브프로세스 관리 및 엔진 추상화 결여**:
   - `llama_manager.py`와 `auxiliary_manager.py`가 개별 하위 프로세스(Subprocess)를 직접 포크/감시하는 구조로 되어 있어, 엔진 교체(vLLM / llama.cpp / SGLang / ONNX) 및 다중 인스턴스 확장이 제한됨.
4. **구조화된 리포트 출력의 제약성**:
   - PILOS 리포트 생성(`REPORT_LLM_OUTPUT_MODE=json_object`) 시 표준 JSON 스키마 제약 디코딩(Grammar Constraint)이 부재하여 파싱 재시도(Retry) 오버헤드가 발생할 수 있음.
5. **동적 VRAM 예산 및 듀얼 상주(Dual-Residence) 지능화**:
   - 2B와 4B 모델 간 동적 전환 시 언로드/리로드가 발생하는데, VRAM 여유 시(5GB 한도 내) 2B+4B 동시 상주(Dual In-Memory) 또는 LRU 정책이 필요함.

### 🎯 최적화 목표
본 명세서는 2026년 최신 추론 엔지니어링 방법론을 도입하여 **① 프리픽스 캐싱 및 청크 프리필을 통한 TTFT 40% 단축**, **② 모듈형 엔진 어댑터(Engine Adapter Pattern) 기반 아키텍처 리팩토링**, **③ 문법 제약 디코딩을 통한 리포트 JSON 생성 무결성 100% 보장**, **④ 실측 VRAM 기반 2B/4B 모델 최적 컨텍스트 윈도우 및 max_tokens 튜닝**을 표준 규격으로 정의합니다.

---

## Clarifications

### Session 2026-08-19 (VRAM 실측 데이터 및 컨텍스트 윈도우 분석)

#### 1. GPU 하드웨어 및 온로드 모델별 실측 VRAM 매트릭스 (GTX 1070 8GB 기준)
- **전체 GPU VRAM**: 8,192 MiB (OS 및 디스플레이 점유 제외 시 CUDA 가용 용량 약 7,100 ~ 7,200 MiB)
- **보조 서비스 상시 점유 VRAM (Port 8090 / 8091)**:
  - BGE-M3 (Q8_0 Embedding, n_ctx=2048): **706 MiB** (기본 가중치 605MB + KV Cache 101MB)
  - BGE-Reranker-v2-m3 (Q8_0 Cross-Encoder, n_ctx=2048): **706 MiB** (기본 가중치 606MB + KV Cache 100MB)
  - 👉 **보조 서비스 고정 점유 총합**: **1,412 MiB (~1.4 GB)**
- **LLM 전용 가용 VRAM**: 가용 7,192MB - 보조 1,412MB = **약 5,780 MiB (~5.6 GB)**

#### 2. 모델별 토큰당 KV Cache 계산 및 16K/12K 컨텍스트 타당성 (2026 최신 리서치 검증)
- **공통 최적화 플래그 (2026 llama.cpp 공식 사양)**:
  - `--cache-prompt`: 동일한 시스템 프롬프트 및 RAG 헤더 재계산 방지 (Prefix Caching)
  - `-fa` (`--flash-attn`): Pascal GPU(GTX 1070 CC 6.1) 전용 벡터 폴백 커널 가속 및 메모리 절감
  - `-ctk q8_0 -ctv q8_0`: KV Cache 8비트 양자화 (FP16 대비 KV 메모리 50% 압축, 무손실에 가까운 정확도 유지)
  - `-b 512 -ub 256`: 청크 프리필(Chunked Prefill) 분할 연산으로 긴 프롬프트 시 TTFT 스파이크 억제
- **Qwen3.5-2B (Q4_K_M)**:
  - 기본 가중치: **1,884 MiB** (1.6 GB)
  - `n_ctx=16,384` (16K, Q8_0 KV): KV Cache **192 MiB** $\rightarrow$ 총 점유 **3,488 MiB (~3.5 GB)** (VRAM 여유 3.6GB!)
  - `max_tokens=8,192`: 긴 수급 통계 및 심층 분석 리포트 전체 수용
  - **판정**: 🟢 **16K 컨텍스트 & 8K 생성 100% 최상 안정 구동**
- **Qwen3.5-4B (Q4_K_M)**:
  - 기본 가중치: **3,297 MiB** (2.8 GB)
  - `n_ctx=12,288` (12K, Q8_0 KV): KV Cache **432 MiB** $\rightarrow$ 총 점유 **5,141 MiB (~5.1 GB)** (VRAM 여유 2.0GB!)
  - `n_ctx=16,384` (16K, Q8_0 KV): KV Cache **576 MiB** $\rightarrow$ 총 점유 **5,285 MiB (~5.3 GB)** (VRAM 여유 1.8GB!)
  - `max_tokens=4,096`: `<think>` 심층 추론(1.5K 토큰) + 최종 답변(1.5K 토큰) 완벽 수용
  - **판정**: 🟢 **12K~16K 컨텍스트 & 4K 생성 100% GPU VRAM 오프로딩 안정 구동**

#### 3. 동적 핫스왑 및 추론 모드 동작 규칙
- **즉시 핫스왑 (0.3s)**: 4B 로드 상태에서 2B 지정 호출 시 10분 유휴 타이머와 무관하게 즉시 0.3초 만에 2B로 스왑하여 요청 처리.
- **유휴 복귀 (10m)**: 4B 사용 후 10분간 추가 요청이 없으면 백그라운드 워치독이 기본 2B 모델로 자동 복귀하여 평상시 VRAM 3.5GB(여유 3.6GB) 유지.
- **가변 추론 모드 (Adaptive Reasoning)**:
  - 고속 응답 필요 시: `skip_thinking=True` (기본 뷰티 챗봇 고속 모드)
  - 심층 논리/성분 비교 시: `skip_thinking=False` (`<think>` 사고 과정 활성화, `think_tag_parser`로 UI 분리 렌더링)

#### 4. RAG 및 챗봇 호출 계층별 컨텍스트 및 Max Tokens 최종 표준 규격
| 모델 역할 | 서버 컨텍스트 (`n_ctx`) | 클라이언트 호출처 | 권장 `max_tokens` | 최적화 사유 |
| :--- | :---: | :--- | :---: | :--- |
| **Qwen3.5-2B**<br/>(Fast / Report) | **16,384** (16K) | PILOS 수급 리포트 배치<br/>고속 챗봇 API | **8,192** (8K) | 대용량 주식 수급 지표(4K) + 완벽한 JSON 리포트(4K) 16K 내 무결 수용 |
| **Qwen3.5-4B**<br/>(Synthesis / Chat) | **12,288** (12K) | Oliview 올리챗 A & 올원챗 B<br/>PILOS 대화형 챗봇 | **4,096** (4K) | 10개 리뷰(3K) + 대화이력(1K) + `<think>` 추론 및 종합 답변(4K) 12K 내 수용 |
| **BGE-M3 / Reranker**<br/>(Auxiliary) | **2,048** (2K) | 검색 및 리랭킹 파이프라인 | N/A | 화장품 리뷰(최대 500토큰) 임베딩/리랭킹에 충분하며 VRAM 1.4GB 고정 절약 |

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - RAG 챗봇 쿼리의 초저지연 첫 토큰(TTFT) 응답 경험 (Priority: P1) 🎯 MVP

올리뷰 챗봇(ChatA, ChatB) 및 PILOS 챗봇 사용자가 질문을 입력했을 때, 공통 시스템 프롬프트 및 RAG 헤더가 프리픽스 캐시에서 즉시 적중(Cache Hit)되어 0.3초 이내에 첫 번째 토큰 스트리밍이 화면에 렌더링되어야 합니다.

**Why this priority**:
대화형 AI 서비스에서 체감 응답 속도를 결정짓는 가장 핵심적인 지표는 TTFT(Time-To-First-Token)이며, RAG의 고정된 시스템 프롬프트 캐싱은 GPU 연산량을 30~50% 절감하는 최우선 과제입니다.

**Independent Test**:
- 동일 시스템 프롬프트 기반 10회 연속 RAG 쿼리 실행 시, 첫 쿼리 대비 2회차 이후 쿼리의 TTFT가 40% 이상 단축(Cache Hit 확인)됨을 벤치마크 테스트로 검증합니다.

**Acceptance Scenarios**:
1. **Given** 동일한 시스템 프롬프트(`당신은 올리뷰...`)를 가진 다수의 질문이 유입될 때, **When** 모델 게이트웨이가 토큰 프리필을 수행하면, **Then** 캐시된 프리픽스 KV 블록을 즉시 재사용하여 프리필 연산 시간을 100ms 미만으로 단축한다.
2. **Given** 2,000토큰 이상의 긴 참조 리뷰 데이터가 입력될 때, **When** 청크 프리필(Chunked Prefill)이 활성화되면, **Then** 대형 토큰 배치로 인한 지연 없이 기존 디코딩 스트림과 균등하게 연산이 분배된다.

---

### User Story 2 - 모듈형 추론 엔진 아키텍처로의 리팩토링 (Priority: P1)

AI 플랫폼 엔지니어는 하드코딩된 서브프로세스 관리 코드 대신, 표준 인터페이스(`BaseInferenceEngine`)를 따르는 **모듈형 엔진 어댑터(Engine Adapter)**를 통해 llama.cpp, vLLM, SGLang 등 임의의 백엔드 엔진을 설정 파일(`config.json`) 한 줄로 교체 및 튜닝할 수 있어야 합니다.

**Why this priority**:
기술 발전 속도가 빠른 LLM 서빙 환경에서 하위 엔진과의 결합도를 낮추고 모듈화해야 향후 최신 하드웨어/엔진 업데이트 시 시스템 전면 재작성을 방지할 수 있습니다.

**Independent Test**:
- 엔진 어댑터 추상화 인터페이스를 통해 엔진 백엔드를 변경하더라도 기존 OpenAI 호환 엔드포인트(`/v1/chat/completions`, `/v1/embeddings`, `/v1/rerank`)의 입출력 계약이 100% 호환됨을 단위/통합 테스트로 검증합니다.

**Acceptance Scenarios**:
1. **Given** 서버가 구동될 때, **When** `engine_type: "llama_cpp"` 또는 `"vllm"` 설정이 지정되면, **Then** 팩토리 패턴을 통해 적절한 엔진 인스턴스가 생성되고 수명주기(Lifespan, Healthcheck, Metrics)가 단일화된 프로토콜로 관리된다.
2. **Given** 임베딩(8090) 및 리랭커(8091) 보조 프로세스가 기동될 때, **When** 예기치 못한 비정상 종료가 발생하면, **Then** 엔진 매니저의 자동 복구 워치독(Auto-Healing Watchdog)이 무중단으로 프로세스를 3초 이내에 재기동한다.

---

### User Story 3 - 구조화된 JSON 리포트 문법 제약 생성 (Priority: P2)

PILOS 시장 수급 분석 워커 및 리포트 생성기가 `REPORT_LLM_MODEL`(Qwen3.5-2B)을 호출하여 JSON 수급 분석 보고서를 생성할 때, 문법 제약(Grammar Constraint / JSON Schema Guided Decoding)을 적용하여 JSON 포맷 파싱 오류율 0%를 달성합니다.

**Why this priority**:
배치 분석 및 자동화 워커에서 LLM 응답이 잘못된 JSON 포맷으로 생성되면 재시도로 인한 시간 낭비 및 데이터 수집 지연이 발생합니다.

**Independent Test**:
- 100회의 PILOS 일일 수급 리포트 생성 배치 실행 시, 단 1건의 JSON 디코딩 실패나 스키마 불일치 없이 100% 유효한 JSON 구조가 수신됨을 검증합니다.

**Acceptance Scenarios**:
1. **Given** 클라이언트가 `response_format: {"type": "json_object"}` 또는 JSON 스키마를 요청할 때, **When** 모델이 토큰을 샘플링하면, **Then** 엔진의 BNF/정규식 문법 마스크가 작동하여 항상 파싱 가능한 유효 JSON 토큰 시퀀스만 출력한다.

---

### User Story 4 - 2026 표준 관측성(OpenTelemetry/Prometheus) 대시보드 고도화 (Priority: P2)

인프라 운영자는 웹 대시보드(`/dashboard`) 및 메트릭스 엔드포인트(`/metrics`)를 통해 실시간 GPU VRAM 점유량, 모델별 TTFT, 초당 생성 토큰 수(TPS), 프리픽스 캐시 히트율, 큐 대기 시간을 직관적으로 모니터링할 수 있습니다.

**Why this priority**:
프로덕션 환경의 병목 지점을 정밀 분석하고 VRAM OOM(Out of Memory) 위험을 사전에 방지하기 위한 필수 관측성 요구사항입니다.

**Independent Test**:
- `/metrics` 프로메테우스 엔드포인트 호출 시 `llm_ttft_seconds`, `llm_tokens_per_second`, `llm_cache_hit_ratio`, `gpu_vram_used_bytes` 메트릭이 1초 주기로 실시간 갱신됨을 검증합니다.

---

## 3. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 LLM 추론 엔진 시작 파라미터에 프리픽스 캐시 활성화 옵션(`--prompt-cache` 및 Prefix Caching)을 기본 적용하여 동일 프롬프트 접두어 재계산을 방지해야 한다.
- **FR-002**: 시스템은 대형 프롬프트 입력 시 지연 스파이크를 방지하기 위해 청크 프리필(Chunked Prefill / Batch Splitting) 설정(`--n-ctx 4096`, `--n-batch 512`, `--n-ubatch 256` 등)을 하드웨어 사양에 맞게 자동 튜닝해야 한다.
- **FR-003**: `model_gateway/src/core/`에 `BaseInferenceEngine` 추상 인터페이스를 신설하고, `LlamaCppEngine`, `AuxiliaryEmbeddingEngine`, `AuxiliaryRerankEngine`을 독립 어댑터 클래스로 리팩토링해야 한다.
- **FR-004**: 모델 로드 매니저는 VRAM 안전 한도(`VRAM_SAFETY_LIMIT_MB`) 내에서 가능한 경우 2B와 4B 모델을 동시 상주(Dual-Residence)시키거나, 초과 시 LRU(Least Recently Used) 기반으로 안전하게 웜 언로드(Warm Eviction)하는 지능형 메모리 풀을 제공해야 한다.
- **FR-005**: `/v1/chat/completions` 엔드포인트는 `response_format` 파라미터(JSON Object / Schema)를 지원하여 문법 제약(Constrained Decoding)을 엔진 레벨에서 강제해야 한다.
- **FR-006**: 보조 서비스(BGE-M3 임베딩 Port 8090, BGE-Reranker Port 8091)의 프로세스 감시 및 자동 복구(Auto-Healing Watchdog) 주기를 5초 단위로 표준화하고 무중단성을 보장해야 한다.
- **FR-007**: 프로메테우스 호환 `/metrics` 엔드포인트를 제공하여 실시간 TTFT, TPS, 캐시 적중률, GPU 메모리 지표를 표준 형식으로 익스포트해야 한다.
- **FR-008**: 모든 리팩토링 후에도 기존 클라이언트(Oliview ChatA, ChatB, PILOS Web, PILOS Worker)와의 HTTP/SSE 통신 계약(`AiGatewayClient`)은 100% 하위 호환성을 유지해야 한다.

---

### Key Entities

- **InferenceEngineAdapter**: 다양한 추론 백엔드(llama.cpp, vLLM 등)를 동일한 수명주기 및 스트리밍 규격으로 제어하는 공통 어댑터.
- **PrefixCacheManager**: 반복되는 시스템 프롬프트 및 RAG 참조 헤더의 KV 캐시 블록 재사용 상태를 추적/관리하는 모듈.
- **MemoryBudgetPool**: GPU VRAM 사용량을 실시간 감시하고 2B/4B/임베딩/리랭커 모델의 상주 우선순위를 제어하는 메모리 관리자.
- **ConstrainedGrammarEngine**: JSON 스키마를 BNF 문법 규칙으로 컴파일하여 유효한 JSON 토큰만 샘플링하도록 제한하는 디코딩 마스크 엔진.

---

## 4. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: **RAG TTFT 40% 이상 단축** - 동일 시스템 프롬프트 기반 2회차 이후 RAG 쿼리의 최초 토큰 응답 시간(TTFT)이 이전 대비 40% 이상 개선되어 350ms 이하를 달성한다.
- **SC-002**: **평균 디코딩 처리 속도(TPS) 25% 향상** - 최적화된 양자화 파라미터 및 배치 튜닝을 통해 초당 생성 토큰 수(Tokens/sec)가 25% 이상 향상된다.
- **SC-003**: **리포트 JSON 생성 무결성 100%** - 100회 연속 PILOS JSON 리포트 생성 테스트에서 JSON 문법 파싱 오류 0건을 달성한다.
- **SC-004**: **무중단 회복력 100%** - 보조 프로세스 강제 종료 시 워치독에 의해 3초 이내에 정상 복구되어 503 에러 없이 서비스를 지속한다.
- **SC-005**: **기존 4개 클라이언트 100% 무결 회귀** - ChatA, ChatB, PILOS Web, PILOS Worker 전체 서비스에서 회귀 결함 0건을 보장한다.

---

## 5. Assumptions

- **A-001**: 호스트 GPU 환경은 NVIDIA CUDA 가속(WSL2 `/dev/dxg` 또는 네이티브 CUDA)을 지원하며 최소 6GB 이상의 VRAM을 확보하고 있다.
- **A-002**: 모델 가중치는 GGUF 고밀도 양자화 포맷(Q4_K_M / Q5_K_M)으로 로컬 `models/` 디렉토리에 보관되어 고속 메모리 맵핑(mmap)이 가능하다.
- **A-003**: 클라이언트 서비스들은 표준 OpenAI 호환 API 규격을 준수하므로 엔드포인트 URL 및 모델명 변경만으로 즉시 연동 가능하다.
