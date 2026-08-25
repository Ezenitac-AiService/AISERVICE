# Implementation Plan: 030-reranker-pipeline-optimization (리랭커 파이프라인 및 LangGraph / Redis 기반 다중 타겟 RAG 오케스트레이션)

**Branch**: `030-reranker-pipeline-optimization` | **Date**: 2026-08-25 | **Spec**: [specs/030-reranker-pipeline-optimization/spec.md](file:///c:/AISERVICE/specs/030-reranker-pipeline-optimization/spec.md)

**Input**: Feature specification from `specs/030-reranker-pipeline-optimization/spec.md`

## Summary

본 기능 계획은 Chatbot A와 Chatbot B의 비정상적인 리랭커 처리(20초 무기한 대기 vs 5초 타임아웃 사일런트 폴백)와 단일 엔티티 추출 편향을 근본적으로 해결하기 위해 수립되었습니다.
2026년 최신 RAG 엔지니어링 패러다임을 전면 도입하여, **LangGraph StateGraph 기반의 다중 타겟 쿼리 오케스트레이터(3대 질의 패턴 라우팅 & `Send` API 병렬 검색)**, **단일 통합 배치 리랭킹(5.0초 단일 타임아웃 & 타겟별 쿼터 파티셔닝)**, **Redis 4단계 다계층 캐시(L1~L4) 및 커넥션 풀 싱글톤**, **Qwen 3.5 2B 16K 대형 컨텍스트(입력 6,000 / 출력 4,096 토큰)**, 그리고 **실시간 계층형 서브스텝 UI 시각화**를 구축합니다.

---

## Technical Context

**Language/Version**: Python 3.12, JavaScript (Vanilla ES6+ for Chatbot B Web UI)  
**Primary Dependencies**: 
- `langgraph >= 0.2.0, < 0.3.0` (선언적 상태 그래프 오케스트레이터)
- `langchain-core >= 0.3.0, < 0.4.0` (메시지 및 런에이블 인터페이스)
- `redis >= 5.0.0` (L1~L4 다계층 인메모리 캐시 및 세션 체크포인터)
- `aiomysql >= 0.2.0` (비동기 MySQL 커넥션 풀)
- `fastapi`, `uvicorn`, `streamlit`, `httpx`, `numpy`  
**Storage**: MySQL 8.0 (Olive Young 화장품 메타데이터 및 250만건 리뷰), ChromaDB (SQLite 벡터 스토어), Redis 7 Alpine (L1~L4 캐시)  
**Testing**: `pytest`, `pytest-asyncio`, E2E 레이턴시 및 정합성 벤치마크 스크립트  
**Target Platform**: Docker 컨테이너 환경 (Linux / Windows WSL2), CUDA 가속 GPU 서빙 게이트웨이  
**Project Type**: Multi-Service AI RAG Web Application & Shared Core Library  
**Performance Goals**: 
- 단일 질의 E2E 응답 시간: **평균 4.5초 이내**
- 다중 비교 질의 E2E 응답 시간: **최대 8.0초 이내** (검색+리랭킹 3.0초 내외)
- 동일/인기 질의 캐시 응답: **0.1초대 (전처리 10ms 이내)**
- 리랭커 실질 적용률: **95% 이상** (사일런트 폴백 0%)
- UI 서브스텝 렌더링 지연: **100ms 이내**  
**Constraints**: 
- 리랭커 단일 표준 타임아웃 5.0초 엄격 준수 (초과 시 0ms 즉각 1차 유사도 순위 유지)
- 입력 컨텍스트 최대 6,000토큰(타겟당 2,000토큰), 최대 생성 토큰 4,096토큰 캡핑 (2K 오버플로우 0건)
- GPU 동시성 제어: `asyncio.Semaphore(3)`로 VRAM OOM 방지
- Redis 소켓 타임아웃: `socket_timeout=0.2s`로 지연 시 즉시 Fail-Fast 무중단 폴백  
**Scale/Scope**: 50개 주요 브랜드, 250만건 리뷰, 2개 챗봇 인터페이스 (Streamlit & FastAPI Web)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 헌법 원칙 (Constitution Principle) | 준수 여부 (Status) | 설계 검증 및 근거 (Design Verification) |
| :--- | :---: | :--- |
| **I. 언어 및 커뮤니케이션 정책** | **PASS** | 사용자 대화, 산출물(`spec.md`, `plan.md`, `tasks.md`), 코드 주석 한국어 작성 준수. 내부 추론 영어 수행. |
| **II. TDD 및 테스트 우선주의** | **PASS** | `contracts/` 스키마 기반 단위/통합 테스트 선행 작성 계획 및 E2E 벤치마크 검증 스위트 정의. |
| **III. 서비스 모듈화 및 격리** | **PASS** | `oliview_core` 공유 라이브러리를 단일 진실 공급원(SSOT)으로 하여 A/B 챗봇이 참조. 기존 GPU 모델 가중치 및 DB 비파괴 보존. |
| **IV. 관측 가능성 및 로깅** | **PASS** | `trace_id` 기반 엔드투엔드 분산 추적, 단계별(검색, 리랭킹, 생성) 레이턴시 JSON 구조화 로깅, 개인정보/민감데이터 마스킹. |
| **V. 단순성 및 점진적 진화 (YAGNI)** | **PASS** | 불필요한 무거운 프레임워크 배제하고 `langgraph` 경량 코어만 핀 고정. `FEATURE_LANGGRAPH_RAG` 핫스왑 롤백 안전망 구축. |

---

## Project Structure

### Documentation (this feature)

```text
specs/030-reranker-pipeline-optimization/
├── spec.md              # 요구사항 명세서 (FR-001 ~ FR-030, SC-001 ~ SC-017)
├── plan.md              # 기술 구현 계획서 (본 파일)
├── research.md          # 5대 핵심 의사결정 및 벤치마크 분석 보고서
├── data-model.md        # RagGraphState, Redis 키 스키마, SubStepEvent 모델
├── quickstart.md        # 테스트 스위트 실행 및 시나리오 검증 가이드
├── contracts/           # API 및 데이터 인터페이스 계약
│   ├── rag-state-schema.json
│   ├── substep-event-schema.json
│   └── api-client-interface.md
├── checklists/
│   └── requirements.md  # 명세서 품질 검증 체크리스트 (16/16 통과)
└── tasks.md             # 구현 태스크 목록 (/speckit-tasks 생성 예정)
```

### Source Code (repository layout)

```text
bteam/
├── oliview_core/                        # 공통 RAG 핵심 엔진 (Single Source of Truth)
│   ├── client.py                        # [MODIFY] AiGatewayClient (Redis L2/L3 캐시 일원화, 5.0s 타임아웃, GPU Semaphore 3)
│   ├── config.py                        # [MODIFY] 16K 토큰 예산, 5.0s 타임아웃, 피처 플래그 설정
│   ├── db_pool.py                       # [NEW] aiomysql 비동기 MySQL 커넥션 풀 싱글톤
│   ├── redis_pool.py                    # [NEW] redis.ConnectionPool 싱글톤 & L1 Single-flight 락
│   ├── alias_dictionary.py              # [NEW] 영문 약칭('CNP'->'차앤박') & 공백 정규화 사전
│   ├── anaphora_resolver.py             # [NEW] Redis L4 대화 히스토리 기반 대명사('그거') 해소기
│   ├── graph_state.py                   # [NEW] RagGraphState Pydantic/TypedDict 정의
│   ├── graph_orchestrator.py            # [NEW] LangGraph StateGraph 오케스트레이터 (3대 패턴 라우팅 & Send 병렬 검색)
│   ├── token_budgeter.py                # [NEW] 6,000토큰 XML 샌드박스 주입 & 제품 스펙 헤더 번들러
│   ├── rerank.py                        # [MODIFY] 단일 통합 배치 리랭킹 & 타겟별 쿼터 파티셔너
│   ├── retrieval.py                     # [MODIFY] 비동기 하이브리드 검색 & L1 풀 캐시 연동
│   ├── guardrail.py                     # [MODIFY] 리뷰 원문 HTML/XML 이스케이핑 보안 추가
│   └── session.py                       # [MODIFY] Redis L4 LangGraph 체크포인터 연동
│
├── Oliview_chatbot_a/                   # Chatbot A (Streamlit)
│   ├── 06.02.app.py                     # [MODIFY] 실시간 계층형 타임라인 UI 및 StreamlitGraphAdapter 연동
│   └── graph_adapter.py                 # [NEW] StreamlitGraphAdapter 동기 제너레이터 래퍼
│
├── Oliview_chatbot_b/                   # Chatbot B (FastAPI Web)
│   ├── project_ragapi.py                # [MODIFY] 독자 HTTP 제거 -> MultiTargetGraphOrchestrator 일원화, SSE 끊김 핸들러
│   └── templates/
│       └── index.html                   # [MODIFY] 프론트엔드 계층형 실시간 타임라인 서브스텝 렌더링
│
└── tests/                               # 자동화 검증 스위트
    ├── unit/
    │   ├── test_graph_orchestrator.py   # [NEW] 3대 라우팅 및 Send 병렬 검색 단위 테스트
    │   ├── test_redis_cache_4tier.py    # [NEW] L1~L4 캐시 히트 및 Fail-Fast 단위 테스트
    │   └── test_reranker_single_batch.py# [NEW] 통합 배치 리랭킹 및 쿼터 파티셔닝 테스트
    └── e2e/
        └── test_latency_parity.py       # [NEW] A/B 챗봇 레이턴시 및 정합성 벤치마크 테스트
```

---

## Component Implementation Strategy

### 1. `oliview_core` 인프라 계층 강화 (`db_pool.py`, `redis_pool.py`, `client.py`)
- `aiomysql` 커넥션 풀(Max 10) 및 `redis.ConnectionPool` 싱글톤 구축.
- `client.py`: 
  - `AiGatewayClient`에 `asyncio.Semaphore(3)` 가드 적용.
  - BGE-Reranker(8091) 호출 시 5.0초 단일 타임아웃 적용 및 로컬 CPU 폴백 제거.
  - Redis L2(임베딩)/L3(리랭킹) 캐시 키 조회 및 저장 일원화.

### 2. 도메인 전처리 및 보안 계층 (`alias_dictionary.py`, `anaphora_resolver.py`, `guardrail.py`)
- `alias_dictionary.py`: 영문 약칭("CNP", "닥터G") 및 공백 불일치 정규화.
- `anaphora_resolver.py`: Redis L4 세션에서 직전 턴 엔티티를 복원하여 "그거" 대명사 자동 해소.
- `guardrail.py`: 리뷰 본문 HTML/XML 이스케이핑(`&lt;`, `&gt;`, `&amp;`) 적용.

### 3. LangGraph StateGraph 오케스트레이터 (`graph_orchestrator.py`, `graph_state.py`)
- `intent_router_node`: 3대 질의 패턴 분류 및 엔티티 유효성 검증.
- `search_subgraph`: `Send` API를 통한 서브 타겟 병렬 검색 및 L1 풀 캐시 조회.
- `reranker_node`: 수집된 후보군 단 1회 통합 배치 리랭킹 및 타겟별 쿼터(상위 2~3건) 파티셔닝.
- `context_builder_node`: 제품 스펙 헤더 번들링 및 6,000토큰 XML 샌드박스 조립.
- `synthesis_stream_node`: Qwen 3.5 2B 실시간 토큰 스트리밍 및 Tier 4 카나리아 검증.

### 4. 프론트엔드 실시간 계층형 인터랙션 (`graph_adapter.py`, `06.02.app.py`, `index.html`)
- **Chatbot A (Streamlit)**: `StreamlitGraphAdapter`를 통해 비동기 이벤트를 동기식으로 수신하여 `st.status()` 하위에 `[1/2] 제품 A 검색 완료(10건)` 서브 항목 실시간 갱신.
- **Chatbot B (FastAPI/SSE)**: SSE 스트리밍 루프에 `await request.is_disconnected()` 취소 가드 적용 및 웹 프론트엔드 동적 타임라인 트리 렌더링.

---

## Complexity Tracking

> Constitution 준수: 불필요한 과도한 추상화 없이 `langgraph` 경량 코어만을 상태 머신으로 활용하며, 비상 시 `FEATURE_LANGGRAPH_RAG=false`로 0초 핫스왑 롤백을 지원하므로 헌법 원칙을 100% 만족함.

| 설계 항목 | 도입 사유 (Why Needed) | 대안 기각 사유 (Why Simpler Alternative Rejected) |
| :--- | :--- | :--- |
| **LangGraph StateGraph** | 3대 쿼리 분기, 다중 타겟 병렬 Map-Reduce 및 실시간 마이크로 이벤트 스트리밍의 무결성 확보 | 순수 `asyncio.gather` 절차적 코드는 상태 동기화 및 에러 격리 코드가 지나치게 비대해짐 |
| **Redis 4-Tier 캐시** | Chatbot B의 캐시 누락 해소 및 반복 질의 0.1초대 고속 응답 보장 | L2/L3만 유지 시 인기 상품 MySQL/내적 연산(50ms) 중복 낭비 지속 |
| **타겟별 쿼터 파티셔닝** | 단일 배치 리랭킹 시 키워드 점수 쏠림으로 인한 특정 제품 인용 증발 방지 | 단순 `ORDER BY score` 적용 시 비교 질의에서 한쪽 제품 리뷰가 0건 인용되는 치명적 결함 발생 |
