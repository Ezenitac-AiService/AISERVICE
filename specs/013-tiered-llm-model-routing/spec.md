# Feature Specification: 013-tiered-llm-model-routing

**Feature Branch**: `013-tiered-llm-model-routing`  
**Created**: 2026-08-19  
**Status**: Draft  
**Input**: User description: "llm 서버의 서비스 모델을 qwen3.5 2b 모델을 기본으로 했어, 각 팀 보고서, 분석서 생성하는 로직과 챗봇과 rag 검색 시스템의 기본 llm 모델도 점검하고, 진짜 고품질 결과가 필요한 부분에만 qwen3.5 4b 모델을 사용하도록 고도화 하는 작업을 위한 리서치를 진행하고 스펙 작성"

---

## 1. 개요 및 배경 (Overview & Background)

현재 통합 AI 서비스 플랫폼(`AISERVICE`)은 A팀(주식 감성 지표 PILOS), B팀(화장품 리뷰 분석 Oliview / OllyChat), 그리고 공통 모델 서빙 게이트웨이(`vllm-serv-gateway`)로 구성되어 있습니다.

전체 워크로드 중 대다수를 차지하는 정기 배치(10분 주기 일별 시장 해설 보고서 생성, 실시간 댓글 전처리/분석) 및 단순 메타데이터 필터링은 초경량 고속 모델인 **`qwen3.5-2b`**로도 충분한 품질과 높은 처리량(70+ tok/s, VRAM ~2.5GB)을 달성할 수 있습니다. 반면, 복잡한 다중 리뷰 종합 비교(RAG Deep Synthesis) 및 심층 투자/제품 상담과 같이 **진짜 고품질의 자연어 추론과 문맥 정렬이 필수적인 핵심 영역**에는 **`qwen3.5-4b`** 모델을 선택적으로 적용하는 **2단계 계층형 모델 라우팅(Tiered LLM Routing) 체계**가 요구됩니다.

본 사양서는 전사 서비스 전반의 모델 사용처를 전수 점검하고, 기본 모델(`qwen3.5-2b`)과 고품질 모델(`qwen3.5-4b`)의 역할을 명확히 분리·고도화하는 기능 요구사항 및 아키텍처 스펙을 정의합니다.

---

## Clarifications

### Session 2026-08-19

- Q: 챗봇 및 RAG 시스템에서 2B(고속 기본)와 4B(고품질 심층) 모델을 분기·전환하는 기준을 어떻게 구성할까요? → A: **기능 단계별 자동 분기** (단순 메타데이터 추출/단순 조회는 `qwen3.5-2b`, RAG 멀티리뷰 종합 합성 및 심층 대화는 `qwen3.5-4b` 자동 호출)
- Q: 4B 모델 호출 중 일시적 VRAM 부족이나 타임아웃 발생 시 Fallback 정책을 어떻게 처리할까요? → A: **자동 2B Fallback** (4B 로드 실패/타임아웃 시 기본 `qwen3.5-2b` 모델로 즉시 자동 대체하여 무중단 서빙 보장)
- Q: 실제 서버 GUI(Windows 데스크톱/IDE/도커) 환경의 가용 VRAM 실측 결과와 임베딩/리랭킹 리소스 정책은? → A: **임베딩/리랭킹 100% CPU·시스템 RAM 분산 (`-ngl 0`) 및 GPU VRAM 단일 전담 최적화**
  - **실측 하드웨어**: NVIDIA GeForce GTX 1070 (8GB VRAM) 중 Windows GUI가 ~2.7GB를 점유하여 실제 순수 AI 가용 VRAM은 **~5.3GB**. 시스템 RAM은 32GB (13.4GB 여유).
  - **임베딩/리랭킹**: `bge-m3`(8090) 및 `bge-reranker-v2-m3`(8091)을 **CPU 및 시스템 RAM으로 완전 오프로드 (`-ngl 0`)**하여 GPU VRAM 점유를 **0 MB**로 격리.
- Q: 2B와 4B 모델의 동시 로드 시 VRAM 절약 및 동시 추론 충돌을 방지하기 위한 운영 방식은? → A: **2B 상시 상주(대형 8K/16K 컨텍스트) + 4B 온디맨드 동시 상주(2K/4K 최적화 컨텍스트) + 추론 상호 배제 락 (Mutual Exclusion Lock)**
  - **2B 모델**: 기본 상시 상주, 대용량 컨텍스트(8,192~16,384 토큰)를 활용하여 대량 배치 보고서 및 넓은 문맥 처리.
  - **4B 모델**: 필요 시 온로드하여 동시 상주, VRAM 과다 점유 방지를 위해 컨텍스트 윈도우를 **2,048~4,096 토큰으로 최적화**하여 KV 캐시 VRAM을 ~0.3GB로 억제.
  - **추론 락 (`_llm_inference_lock`)**: 게이트웨이 레벨에서 2B와 4B의 동시 GPU 연산(CUDA 충돌 및 피크 VRAM 폭증)을 방지하는 상호 배제 락을 적용하여, 한 모델이 추론 중일 때 다른 모델 요청은 메모리 스왑 없이 1~2초 대기 큐잉 후 순차 처리.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 고속 기본 서빙 및 대용량 배치 처리 (Tier 1: Fast Base Model - `qwen3.5-2b`) (Priority: P1)

시스템 운영자는 대량의 주기적 데이터 생성 작업(A팀 10개 종목 10분 주기 일별 시장 해설 보고서 생성, 단일 댓글 실시간 감성 분석, B팀 챗봇 질의 메타데이터 추출 및 의도 분류)에 가볍고 빠른 `qwen3.5-2b`를 기본 모델로 배정하여, GPU VRAM 점유를 최소화하고 지연 시간을 1~2초 내외로 유지합니다.

**Why this priority**:
배치 파이프라인의 처리 속도와 서버 안정성(VRAM OOM 방지)을 보장하고, 서비스 전반의 기본 응답 속도를 극대화하기 위한 핵심 기반입니다.

**Independent Test**:
A팀 `generate_llm_reports.py` 실행 및 B팀 메타데이터 필터링 호출 시 `qwen3.5-2b`를 통해 건당 2초 미만의 속도로 정상 완료되는지 독립적으로 검증합니다.

**Acceptance Scenarios**:
1. **Given** 10개 종목에 대한 일별 시장 해설 보고서 생성 배치가 시작될 때, **When** 모델 게이트웨이에 보고서 생성을 요청하면, **Then** 기본 모델인 `qwen3.5-2b`로 라우팅되어 종목당 평균 1~2초 내에 JSON 스키마 규격의 보고서가 성공적으로 생성되어야 합니다.
2. **Given** 사용자가 B팀 OllyChat에 제품 관련 질문을 입력할 때, **When** 질문에서 피부 타입, 제형, 카테고리 등 메타데이터 조건을 추출할 때, **Then** `qwen3.5-2b`가 호출되어 0.5초 이내에 추출 결과를 반환해야 합니다.

---

### User Story 2 - RAG 멀티리뷰 심층 비교 및 고품질 전문가 상담 (Tier 2: Deep Synthesis Model - `qwen3.5-4b`) (Priority: P1)

B팀 화장품 추천 챗봇(OllyChat) 사용자 및 A팀 심층 주식 분석 사용자는 단순 조회를 넘어 여러 리뷰를 종합 비교하거나 다각도의 심층 인사이트를 질의할 때, 고품질 추론 모델인 `qwen3.5-4b`를 통해 풍부하고 자연스러운 한국어 합성 답변을 제공받습니다.

**Why this priority**:
최종 사용자가 체감하는 AI 서비스의 신뢰도와 답변 품질을 결정짓는 핵심 가치 영역입니다.

**Independent Test**:
B팀 RAG 검색 후 5개 이상의 리뷰가 Context로 주어졌을 때 `qwen3.5-4b`를 통해 환각(Hallucination) 없이 유기적인 장단점 비교 답변이 생성되는지 독립 테스트합니다.

**Acceptance Scenarios**:
1. **Given** B팀 OllyChat에서 검색된 다수의 제품 리뷰 문맥이 준비되었을 때, **When** 최종 RAG 답변 합성을 요청하면, **Then** `qwen3.5-4b`가 호출되어 문맥에 충실하고 논리적인 고품질 한국어 추천/비교 답변을 생성해야 합니다.
2. **Given** A팀 챗봇에서 사용자가 복합적인 시장 요인과 종목 간 상관관계에 대한 심층 질문을 입력할 때, **When** 심층 분석 질의로 분류되면, **Then** `qwen3.5-4b`로 라우팅되어 전문적인 인사이트 답변을 생성해야 합니다.

---

### User Story 3 - 모델 게이트웨이 지능형 동적 라우팅 및 자원 안전성 보장 (Priority: P2)

공통 모델 게이트웨이(`vllm-serv-gateway`)는 클라이언트가 요청하는 모델(`qwen3.5-2b` vs `qwen3.5-4b`)에 따라 적절한 인스턴스로 분기 처리하며, 잦은 모델 스위칭에 따른 오버헤드와 VRAM 충돌을 방지합니다.

**Why this priority**:
2B와 4B 모델이 공존하는 다중 컨테이너 환경에서 GPU VRAM 안정성과 무중단 서빙을 유지하기 위함입니다.

**Independent Test**:
동시에 2B 요청(보고서 배치)과 4B 요청(챗봇 심층 답변)이 유입될 때 에러나 GPU OOM 없이 순차/병렬 처리되는지 테스트합니다.

**Acceptance Scenarios**:
1. **Given** 모델 게이트웨이가 가동 중일 때, **When** 클라이언트가 `model: "qwen3.5-2b"` 또는 `model: "qwen3.5-4b"`를 명시하여 호출하면, **Then** 모델 게이트웨이는 요청된 모델 규격으로 정상 응답을 반환해야 합니다.
2. **Given** 4B 모델 호출 중 일시적인 자원 부족이나 타임아웃이 발생할 경우, **When** 에러 핸들러가 동작하면, **Then** 2B 기본 모델로 안전하게 Fallback 하거나 명확한 재시도 안내를 반환해야 합니다.

---

### User Story 4 - 전사 통합 환경변수 및 서비스 설정 일원화 (Priority: P2)

개발자 및 배포 운영자는 전사 루트 `.env`, `docker-compose.yml`, A팀/B팀 config 파일에서 모델명을 체계적으로 관리할 수 있으며, 코드 수정 없이 환경변수 변경만으로 각 작업별 할당 모델을 제어할 수 있습니다.

**Why this priority**:
하드코딩된 모델 호출을 제거하고 유지보수성 및 운영 유연성을 확보하기 위함입니다.

**Independent Test**:
환경변수 `FAST_LLM_MODEL`과 `SYNTHESIS_LLM_MODEL` 값을 변경했을 때 각 팀 서비스가 변경된 설정값을 정확히 참조하는지 확인합니다.

**Acceptance Scenarios**:
1. **Given** 루트 `.env` 파일에 `FAST_LLM_MODEL=qwen3.5-2b`, `SYNTHESIS_LLM_MODEL=qwen3.5-4b`가 정의되어 있을 때, **When** 각 서비스 컨테이너가 기동되면, **Then** A팀/B팀 백엔드 및 워커가 해당 환경변수를 주입받아 정확한 모델로 요청을 전송해야 합니다.

---

### Edge Cases

1. **VRAM 경계 조건 및 OS 안전 마진**: 임베딩 및 리랭킹 모델이 CPU 및 시스템 RAM으로 완전 분산(0MB VRAM)된 상태에서, 2B와 4B 모델 공존 시 총 GPU VRAM 점유량은 **최대 5.0GB 이하**로 엄격히 제한되어 Windows GUI(~2.7GB) 환경에서도 최소 300MB 이상의 안전 마진을 유지해야 합니다.
2. **RAG 프롬프트 컨텍스트 초과 방지 (Context Budget Guardrail)**: 4B 모델의 컨텍스트 윈도우(2K~4K) 초과 에러를 방지하기 위해, B팀 RAG 컨텍스트 빌더는 4B에 전달되는 검색 리뷰 본문과 프롬프트 총합이 **최대 1,500 토큰을 넘지 않도록 사전 슬라이싱 가드레일**을 적용해야 합니다.
3. **인터랙티브 선점 스케줄링 (Batch Preemption)**: A팀 10개 종목 배치 보고서 생성(25초 소요) 중 웹 챗봇 요청이 유입될 경우, 진행 중인 종목 단 1건(1~2초) 완료 직후 즉시 챗봇 요청을 우선 가로채어(Preempt) 처리함으로써 사용자 대기 시간을 2초 이내로 방어해야 합니다.
4. **LLM 응답 스키마 불일치 및 Fallback 템플릿**: 2B 모델 출력 시 `response_format: {"type": "json_object"}`를 강제하고, Pydantic/Validator 검증 실패 시 최대 2회 재시도 후 표준 템플릿으로 안전 처리합니다.

---

## 3. 전사 서비스별 LLM 모델 할당 매트릭스 (Service Model Assignment Matrix)

| 구분 | 서비스/모듈 | 담당 기능 | 권장 모델 | 선정 사유 |
|---|---|---|:---:|---|
| **공통 인프라** | `vllm-serv-gateway` | OpenAI 호환 엔드포인트 | `qwen3.5-2b` (기본)<br>`qwen3.5-4b` (심층) | GPU 가용 VRAM 5.3GB 집중 활용 |
| **공통 인프라** | `bge-m3` | 텍스트 임베딩 (8090 포트) | `bge-m3` | **CPU/시스템 RAM 100% 전담 (`-ngl 0`)**, GPU VRAM 0MB |
| **공통 인프라** | `bge-reranker-v2-m3` | 교차 인코더 리랭킹 (8091 포트) | `bge-reranker-v2-m3` | **CPU/시스템 RAM 100% 전담 (`-ngl 0`)**, GPU VRAM 0MB |
| **A-Team (PILOS)** | `generate_llm_reports.py` | 10분 주기 10개 종목 일별 해설 보고서 생성 | **`qwen3.5-2b`** | 10분 주기 대량 생성 속도(1~2초), 엄격한 JSON 스키마 준수 |
| **A-Team (PILOS)** | `single_comment_service.py` | 사용자 단일 댓글 실시간 감성 분석 | **`qwen3.5-2b`** | 즉시성(밀리초 단위 응답) 및 키워드 추출 |
| **A-Team (PILOS)** | `chatbot_service.py` (일반) | 주가 조회, 당일 신호 점수, 단순 Q&A | **`qwen3.5-2b`** | 저지연 실시간 대화 응답 |
| **A-Team (PILOS)** | `chatbot_service.py` (심층) | 종목 간 비교, 다일간 수급 추세 심층 해설 | **`qwen3.5-4b`** | 복합 문맥 추론 및 정밀 투자 인사이트 합성 |
| **B-Team (Oliview)** | `05.chatbot.py` (필터) | 사용자 질문 메타데이터/필터 조건 추출 | **`qwen3.5-2b`** | 빠른 의도 파악 및 JSON 필터링 |
| **B-Team (Oliview)** | `05.chatbot.py` (합성) | RAG 다중 리뷰 종합 비교 및 맞춤 추천 | **`qwen3.5-4b`** | **[핵심 고품질]** 5~10개 리뷰 교차 검증 및 자연스러운 문장 생성 |
| **B-Team (Oliview)** | `project_ragapi.py` | 올리뷰 챗봇 백엔드 API 서비스 | **`qwen3.5-4b`** | 최종 사용자 대상 고품질 응답 합성 |

---

## 4. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 기본 LLM 모델(`FAST_LLM_MODEL`)로 `qwen3.5-2b`를 사용하고, 고품질 합성 모델(`SYNTHESIS_LLM_MODEL`)로 `qwen3.5-4b`를 명시적으로 분리 정의해야 합니다.
- **FR-002**: 임베딩(`bge-m3`, 8090 포트)과 리랭커(`bge-reranker-v2-m3`, 8091 포트)는 GPU VRAM을 0MB 사용하도록 **CPU 및 시스템 RAM 전담(`-ngl 0` / `--n-gpu-layers 0`)**으로 기동해야 합니다.
- **FR-003**: A팀 정기 보고서 생성(`pilos/jobs/generate_llm_reports.py`) 및 단일 댓글 분석은 GPU 가속 `qwen3.5-2b`를 호출하여 실행되어야 합니다.
- **FR-004**: B팀 RAG 챗봇(`05.chatbot.py`, `project_ragapi.py`)의 다중 리뷰 기반 최종 답변 합성 단계는 `qwen3.5-4b`를 호출하여 고품질 결과를 생성해야 합니다.
- **FR-005**: B팀 질문 전처리 및 메타데이터 필터링 단계는 `qwen3.5-2b`를 호출하여 0.5초 이내에 필터 조건을 추출해야 합니다.
- **FR-006**: 모델 게이트웨이(`vllm-serv-gateway`)는 `GET /v1/models` 요청 시 `qwen3.5-2b`, `qwen3.5-4b`, `bge-m3`, `bge-reranker-v2-m3`의 가용 상태를 정확히 제공해야 합니다.
- **FR-007**: 모든 LLM 호출 모듈은 응답 내 불필요한 `<think>` 태그 또는 CoT 잔여물을 자동으로 세척(`clean_think_tags`)해야 합니다.
- **FR-008**: 구조화된 JSON 출력이 필요한 단계는 `response_format={"type": "json_object"}` 옵션을 표준 적용해야 합니다.
- **FR-009**: 챗봇 및 RAG 시스템은 사용자 질문의 복잡도와 처리 파이프라인 단계(메타데이터 추출 vs 최종 멀티리뷰 종합 합성)에 따라 `qwen3.5-2b`와 `qwen3.5-4b`를 자동으로 분기 호출해야 합니다.
- **FR-010**: `qwen3.5-4b` 호출 시 일시적인 VRAM 부족, 핫스왑 지연 또는 타임아웃이 발생하면 기본 `qwen3.5-2b` 모델로 즉시 자동 Fallback 재시도하여 사용자 무중단 응답을 보장해야 합니다.
- **FR-011**: 게이트웨이(`vllm-serv-gateway`)는 2B와 4B 모델의 동시 GPU 연산 충돌 및 피크 VRAM 폭증을 방지하기 위해 **추론 상호 배제 락(`_llm_inference_lock`)**을 적용하여, 한 모델이 추론 중일 때 다른 모델 요청을 메모리 언로드 없이 순차 큐잉 처리해야 합니다.
- **FR-012**: 5.3GB 가용 VRAM 내 안정적 공존을 위해 `qwen3.5-2b`는 8K~16K의 대용량 컨텍스트 윈도우를 기본 부여하고, `qwen3.5-4b`는 2K~4K로 컨텍스트 윈도우를 최적화하여 KV 캐시 VRAM 점유를 최소화해야 합니다.
- **FR-013**: 사용자 대화 지연(Starvation)을 방지하기 위해, 웹 챗봇 등 인터랙티브 요청(`priority: high`)이 백그라운드 10분 배치 작업(`priority: low`)보다 우선 처리되도록 **우선순위 기반 선점 큐(Priority Preemption Queue)**를 지원해야 합니다.
- **FR-014**: 제한된 VRAM 환경에서 KV 캐시 메모리 점유를 최대 50% 이상 압축하기 위해 **양자화된 KV 캐시(`--ctk q8_0 --ctv q8_0`)**를 모델 서빙 엔진 파라미터로 적용해야 합니다.
- **FR-015**: 반복되는 시장 보고서 지시문 및 챗봇 페르소나의 중복 연산을 제거하여 TTFT(첫 토큰 도달 시간)를 단축하기 위해 **프롬프트 캐싱(Prompt Caching)**을 기본 활성화해야 합니다.
- **FR-016**: B팀 RAG 컨텍스트 빌더는 4B 모델 호출 시 프롬프트 및 리뷰 총 토큰 수가 **최대 1,500 토큰**을 초과하지 않도록 엄격한 사전 예산(Budgeting) 가드레일을 적용해야 합니다.
- **FR-017**: 4B 모델이 10분 이상 연속 유휴(Idle) 상태일 경우 VRAM을 안전하게 해제하여 2B 모델의 버퍼 공간을 100% 확보하는 **유휴 리소스 동적 회수(Idle Reclamation)**를 지원해야 합니다.
- **FR-018**: 모델 게이트웨이는 실시간 GPU VRAM 점유량, 활성 로드 모델, 대기 큐 크기를 모니터링할 수 있는 **관측 엔드포인트(`GET /health/vram`)**를 제공해야 합니다.

### Key Entities

- **Model Routing Tier**:
  - `tier_name`: "fast" (`qwen3.5-2b`) vs "deep" (`qwen3.5-4b`)
  - `target_services`: 할당 서비스 목록
  - `max_context_length`: 8K~16K (2B) / 2K~4K (4B)
  - `target_latency`: <2s (2B) / <5s (4B)
- **Service Configuration**:
  - `FAST_LLM_MODEL`: "qwen3.5-2b"
  - `SYNTHESIS_LLM_MODEL`: "qwen3.5-4b"
  - `EMBEDDING_MODEL`: "bge-m3"
  - `RERANK_MODEL`: "bge-reranker-v2-m3"

---

## 5. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A팀 10개 종목 일별 시장 해설 보고서 10건 전체 생성이 25초 이내에 완료되어야 합니다 (종목당 평균 2.5초 이하).
- **SC-002**: B팀 OllyChat RAG 질의 시 메타데이터 필터 추출 지연시간이 0.5초 이내여야 합니다.
- **SC-003**: B팀 OllyChat의 5개 이상 리뷰 기반 고품질 합성 답변(`qwen3.5-4b`) 생성이 5초 이내에 완료되어야 하며, 환각이나 문맥 이탈이 없어야 합니다.
- **SC-004**: 전체 서비스 동시 운영 시 GPU VRAM 사용량이 **5.0GB 이하**로 통제되어 Windows GUI 환경에서도 OOM 크래시 없이 안정적으로 영구 가동되어야 합니다.

---

## 6. Assumptions

- 모델 서빙 게이트웨이(`vllm-serv-gateway`)는 로컬 또는 도커 내부망(`http://vllm-serv-gateway:8081`)을 통해 OpenAI 호환 규격으로 통신합니다.
- `qwen3.5-2b`와 `qwen3.5-4b` GGUF 가중치 파일이 `model_gateway/models/` 디렉토리에 정상 준비되어 있습니다.
- 임베딩(8090)과 리랭킹(8091) 서비스는 전용 포트에서 독립 프로세스로 상시 가동됩니다.
