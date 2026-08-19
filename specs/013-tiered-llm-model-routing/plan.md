# Implementation Plan: 013-tiered-llm-model-routing

**Branch**: `013-tiered-llm-model-routing` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/013-tiered-llm-model-routing/spec.md` and research findings from `specs/013-tiered-llm-model-routing/research.md`

---

## Summary

전사 AI 서비스(A팀 시장 감성 지표 PILOS, B팀 화장품 리뷰 분석 Oliview / OllyChat, 공통 모델 게이트웨이)의 LLM 자원을 최적화하기 위해, **기본 초고속 처리 모델(`qwen3.5-2b`, 8K~16K 컨텍스트)**과 **고품질 심층 합성 모델(`qwen3.5-4b`, 2K~4K 컨텍스트)**을 기능 단계별로 자동 분기하는 **2단계 계층형 모델 라우팅(Tiered LLM Routing) 아키텍처**를 구현합니다.

실측 가용 GPU VRAM 5.3GB(GTX 1070 8GB, Windows GUI 2.7GB 점유) 한도를 준수하기 위해 임베딩(`bge-m3`)과 리랭커(`bge-reranker-v2-m3`)를 CPU/시스템 RAM(32GB)으로 100% 오프로드(`-ngl 0`)하고, 모델 게이트웨이에 **추론 상호 배제 락(`_llm_inference_lock`)** 및 **인터랙티브 선점 큐(Priority Preemption Queue)**, **Q8_0 KV 캐시 압축**, **프롬프트 캐싱**을 적용하여 GPU VRAM을 **5.0GB 이하로 엄격히 통제**하면서 0초 핫스왑 지연과 무중단 Fallback을 보장합니다.

---

## Technical Context

**Language/Version**: Python 3.12 (Model Gateway), Python 3.11 (A-Team / B-Team)  
**Primary Dependencies**: FastAPI, Uvicorn, httpx, llama-cpp-python / llama-server, Pydantic v2, pytest, asyncio  
**Storage**: MySQL 8.0 (`pilos_v2`, `oliview_project`), Chroma Vector DB, Redis / In-Memory Priority Queue  
**Testing**: `pytest tests/test_tiered_routing_contract.py` (Contract), 단위/통합 테스트 스위트  
**Target Platform**: Linux Container on WSL2 (Docker / Windows host NVIDIA GeForce GTX 1070 8GB)  
**Project Type**: Multi-service microservices & API Gateway (`aiservice-network`)  
**Performance Goals**:
- A팀 10개 종목 10분 주기 일괄 보고서 생성: 25초 이내 (종목당 <2.5초)
- B팀 챗봇 메타데이터 필터링 지연시간: <0.5초
- B팀 OllyChat 5개 이상 다중 리뷰 RAG 고품질 합성: <5.0초
- 사용자 인터랙티브 챗봇 선점 대기시간: <2.0초
**Constraints**:
- 총 GPU VRAM 점유량: **<= 5.0 GB** (Windows GUI 2.7GB 상시 점유 시 안전 마진 >= 300MB)
- 4B 프롬프트 입력 예산: **<= 1,500 토큰** (4B 2K/4K 컨텍스트 오버플로우 방어)
- 임베딩/리랭커 GPU 점유: **0 MB** (CPU 100% 전담 `-ngl 0`)
**Scale/Scope**: 10개 주식 종목 상시 배치, 10,000+ 화장품 리뷰 벡터 검색, 실시간 웹 챗봇

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 헌법 원칙 | 준수 여부 | 설계 반영 상세 |
|---|:---:|---|
| **I. 언어 정책 (Korean/English)** | PASS | 모든 문서, 명세, 계약서, 주석은 한국어로 작성하며 내부 추론은 영어로 수행 |
| **II. TDD 및 계약 검증 (Test-First)** | PASS | Phase 1에서 `/contracts/` 인터페이스 정의 후 계약 테스트(`test_tiered_routing_contract.py`) 선행 구축 |
| **III. 모듈화 및 비파괴성 (Isolation)** | PASS | 기존 바이너리/모델 가중치 보존, A팀/B팀 독립 컨테이너 격리 및 환경변수 일원화 |
| **IV. 관측성 및 로깅 (Observability)** | PASS | `GET /health/vram` 엔드포인트 신설, 구조화된 모델 라우팅 로그 및 지연시간 추적 |
| **V. 단순성 및 점진성 (YAGNI)** | PASS | 복잡한 외부 분산 오케스트레이터 대신 검증된 FastAPI 경량 우선순위 큐 및 프로세스 락 채택 |

---

## Project Structure

### Documentation (this feature)

```text
specs/013-tiered-llm-model-routing/
├── spec.md              # 요구사항 명세서 (FR-001 ~ FR-018)
├── research.md          # 2026 최신 트렌드 및 타당성 분석서 (Phase 0)
├── plan.md              # 본 구현 계획서 (Phase 1)
├── data-model.md        # 데이터 모델 및 설정 스키마 (Phase 1)
├── quickstart.md        # 엔드투엔드 검증 가이드 (Phase 1)
├── contracts/           # 인터페이스 계약서 (Phase 1)
│   ├── model_gateway_routing_contract.md
│   ├── priority_inference_queue_contract.md
│   └── service_configuration_contract.md
├── checklists/
│   └── requirements.md  # 품질 검증 체크리스트
└── tasks.md             # 작업 분할 및 의존성 트리 (/speckit-tasks 산출물)
```

### Source Code Impact Matrix

```text
c:\AISERVICE/
├── .env / .env.example                          # 전사 공통 모델 환경변수 (FAST_LLM_MODEL, SYNTHESIS_LLM_MODEL)
├── docker-compose.yml                           # 각 서비스 컨테이너 환경변수 주입 매핑
│
├── model_gateway/                               # 공통 모델 서빙 게이트웨이
│   ├── config/server_config.json                # CPU 오프로딩(-ngl 0), Q8_0 KV캐시, 차등 컨텍스트 설정
│   ├── src/core/
│   │   ├── auxiliary_manager.py                 # bge-m3/reranker CPU 모드(-ngl 0) 강제
│   │   ├── process_manager.py                   # --ctk q8_0 --ctv q8_0 파라미터 주입 및 VRAM 검증
│   │   └── scheduler.py                         # [NEW] 우선순위 선점 큐 및 인터랙티브 스케줄러
│   └── src/api/routes/
│       ├── inference_api.py                     # 우선순위 라우팅, 프롬프트 캐싱, 즉시 2B Fallback
│       └── health_api.py                        # GET /health/vram 모니터링 엔드포인트
│
├── ateam/pilos-sentiment-index/                 # A-Team (PILOS)
│   ├── pilos/collection/ai_clients/
│   │   └── llm_report_client.py                 # FAST_LLM_MODEL (qwen3.5-2b) 표준화 및 priority: low 전송
│   ├── pilos/service/
│   │   ├── chatbot_service.py                   # 단순 조회(2B, high) vs 복합 심층 질의(4B, high) 분기
│   │   └── single_comment_service.py            # FAST_LLM_MODEL (2B, high) 실시간 감성 분석
│   └── pilos/jobs/
│       └── generate_llm_reports.py              # 배치 보고서 생성 시 2B 호출 및 실패 복구 템플릿
│
├── bteam/                                       # B-Team (Oliview / OllyChat)
│   ├── Oliview_chatbot_a/
│   │   ├── config.json                          # fast_llm_model(2B), synthesis_llm_model(4B) 일원화
│   │   ├── 05.chatbot.py                        # 메타데이터 필터(2B) vs 다중리뷰 합성(4B, 1500토큰 가드)
│   │   └── llm_common.py                        # 4B 타임아웃 시 2B 즉시 Fallback 래퍼
│   └── Oliview_chatbot_b/
│       └── project_ragapi.py                    # RAG 챗봇 API 4B 합성 및 1,500 토큰 슬라이싱
│
└── tests/
    └── test_tiered_routing_contract.py          # [NEW] 2-Tier 라우팅, 우선순위 큐, Fallback 계약 검증 테스트
```

---

## Implementation Phases

### Phase 0: Outline & Research (완료)
- `specs/013-tiered-llm-model-routing/research.md` 작성 완료 (2026 최신 트렌드, K-Quant KV캐시, 선점 큐, 프롬프트 캐싱 분석 반영).

### Phase 1: Design & Contracts (본 단계)
- `data-model.md`: 모델 티어 스키마, 큐 아이템 페이로드, VRAM 메트릭 엔티티 정의
- `contracts/`: 게이트웨이 라우팅, 우선순위 큐, 서비스 설정 규격 계약서 작성
- `quickstart.md`: 단계별 검증 시나리오 및 curl/pytest 검증 명령 가이드 작성

### Phase 2: Tasks Decompostion (Next `/speckit-tasks`)
- 의존성 순서에 따른 실행 태스크 목록 생성 (`tasks.md`)

---

## Regression Testing Plan (전사 기존 기능 통합 회귀 테스트 계획)

구현 완료 후 2-Tier 라우팅 및 CPU 오프로딩 적용으로 인해 기존 정상 서비스에 부작용이나 기능 퇴행(Regression)이 발생하지 않았는지 확인하기 위해 다음 4대 영역 12개 테스트 시나리오를 전수 수행합니다.

### 1. A-Team (PILOS 감성 지표 서비스) 회귀 검증
- [ ] **REG-A1 (10분 주기 파이프라인 자동화)**: `pilos_worker` 데몬이 중단 없이 정상 실행되며 `service_pipeline_run` 상태가 `completed`로 완료되는가?
- [ ] **REG-A2 (10개 종목 시장 해설 보고서 생성)**: `GET /api/stocks/{code}/llm-reports?model_date=2026-08-19` 호출 시 10개 전 종목의 보고서가 `qwen3.5-2b`를 통해 누락 없이 정상 반환되는가?
- [ ] **REG-A3 (실시간 단일 댓글 감성 분석)**: `POST /api/sentiment/single-comment` 호출 시 2B 모델을 통해 밀리초 단위로 긍정/부정 점수 및 키워드가 분석되는가?
- [ ] **REG-A4 (PILOS 웹 대시보드 및 챗봇)**: `https://ezenitac.duckdns.org/ateam/pilos/` 웹 대시보드 상태 배너가 '정상 가동 중'이며, 챗봇 질의응답이 정상 동작하는가?

### 2. B-Team (Oliview / OllyChat 화장품 분석 & 챗봇) 회귀 검증
- [ ] **REG-B1 (제품 상세 및 리뷰 분석 라우팅)**: `https://ezenitac.duckdns.org/bteam/`에서 제품 목록 조회, 상세 페이지 이동 및 감성 분석 차트가 정상 렌더링되는가?
- [ ] **REG-B2 (올리챗 메타데이터 추출)**: 사용자 질의(예: "지성 피부 진정 세럼") 입력 시 `qwen3.5-2b`가 0.5초 이내에 필터 조건을 정상 파싱하는가?
- [ ] **REG-B3 (RAG 다중 리뷰 종합 합성)**: Chroma 벡터 검색 + BGE 리랭킹 후 5개 리뷰 기반으로 `qwen3.5-4b`가 고품질 종합 비교 답변을 생성하는가?
- [ ] **REG-B4 (4B 장애 시 2B 무중단 Fallback)**: 4B 의도적 비가용 시에도 사용자 화면에 에러 없이 2B 모델로 대체 답변이 렌더링되는가?

### 3. 공통 인프라 (Model Gateway & Nginx Reverse Proxy) 회귀 검증
- [ ] **REG-G1 (CPU 임베딩 서버 8090)**: `POST http://vllm-serv-gateway:8090/embedding` 호출 시 `bge-m3` 임베딩 벡터(1024차원)가 정상 생성되며 GPU VRAM 점유가 0MB인가?
- [ ] **REG-G2 (CPU 리랭커 서버 8091)**: `POST http://vllm-serv-gateway:8091/rerank` 호출 시 `bge-reranker-v2-m3` 관련도 스코어가 정상 반환되며 GPU VRAM 점유가 0MB인가?
- [ ] **REG-G3 (실시간 VRAM 상한선 모니터링)**: `GET http://vllm-serv-gateway:8081/health/vram` 호출 시 `gpu_vram_used_mb <= 5000` 안전 기준을 상시 만족하는가?
- [ ] **REG-G4 (통합 포털 2x2 그리드 게이트웨이)**: `https://ezenitac.duckdns.org/` 메인 포털에서 A팀(PILOS) 및 B팀(Oliview, OllyChat A/B) 4개 서비스 링크가 404 없이 모두 정상 연결되는가?

---

## Complexity Tracking

| 설계 항목 | 도입 사유 | 대안 기각 사유 |
|---|---|---|
| **우선순위 선점 큐 (Priority Queue)** | 25초 배치 중 챗봇 사용자 멈춤(Starvation) 방지 | 단순 FIFO 락은 사용자 응답 지연을 최대 20초 유발하여 불가 |
| **KV 캐시 Q8_0 양자화** | 5.3GB 제한 VRAM 내 2B/4B 안전 공존 | FP16 KV 캐시는 VRAM 1.2GB를 추가 소모하여 5.0GB 한도 초과 |
| **RAG 1,500 토큰 가드레일** | 4B 2K/4K 컨텍스트 오버플로우 원천 방어 | 가드레일 부재 시 긴 리뷰 유입 시 HTTP 400 에러 발생 |
