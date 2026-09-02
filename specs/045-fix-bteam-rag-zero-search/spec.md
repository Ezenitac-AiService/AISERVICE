# Feature Specification: Oliview B-Team RAG 파이프라인 DB/리랭커 복구 및 64K q8_0 KV 양자화 OOM 방지 (Fix B-Team RAG Zero-Search & 64K q8_0 Quantized OOM Prevention)

**Feature Branch**: `045-fix-bteam-rag-zero-search`

**Created**: 2026-09-02

**Status**: Clarified (Ready for Planning)

**Input**: User inquiry: "왜 정상화가 안되었을까? Oliview 챗봇 A, B에서 '자극 없이 순한 클렌징 제품 분석해줘', '여름철 기름기 잡고 모공 커버 잘되는 매트한 파운데이션 추천해줘' 질의 시 0건 부재 고지 발생"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 올리뷰 챗봇 A & B 실시간 리뷰 기반 RAG 분석 답변 정상 수신 (Priority: P1)

올리뷰 챗봇 사용자(웹 UI 및 Streamlit 클라이언트)가 챗봇 A 또는 챗봇 B를 통해 질문을 입력했을 때, 챗봇이 0건 부재 고지 대신 실제 올리브영 데이터베이스의 리뷰 데이터를 검색·리랭킹하여 화장품 속성별 심층 분석 답변과 참고 리뷰 인라인 인용을 정상적으로 생성·제공받는다.

**Why this priority**: 챗봇 A와 B 모두에서 유효한 질문에 데이터가 없다는 0건 부재 고지가 뜨는 것은 서비스 핵심 기능의 완전 마비이므로 최우선 해결해야 한다.

**Independent Test**: Oliview 챗봇 A 및 챗봇 B UI/API로 각각 대표 질의를 실행하여, 0건 부재 고지 없이 정상적인 AI 생성 답변과 참고 리뷰 목록(5건)이 반환되는지 검증한다.

**Acceptance Scenarios**:

1. **Given** 올리뷰 챗봇 A가 실행 중일 때, **When** 사용자가 "브링그린 클렌징 제품 모공 세정 효과 알려줘"를 입력하면, **Then** 0건 부재 고지 없이 실제 리뷰를 바탕으로 세정력/자극성 분석 결과가 생성되어야 한다.
2. **Given** 올리뷰 챗봇 B가 실행 중일 때, **When** 사용자가 "여름철 기름기 잡고 모공 커버 잘되는 매트한 파운데이션 추천해줘"를 입력하면, **Then** SQL 메타데이터 조회 에러 없이 추천 상품 및 리뷰 분석 답변이 스트리밍되어야 한다.

---

### User Story 2 - 64K 풀 컨텍스트 유지 및 q8_0 KV 캐시 양자화를 통한 Kernel OOM 방지 (Priority: P2)

기본 초고속 모델(`qwen3.5-2b`)이 64K (65,536) 풀 컨텍스트 윈도우를 유지하면서도, 보조 모델(임베딩 8090, 리랭커 8091) 3종이 동시 상주할 때 시스템 RAM/VRAM 고갈로 인한 Linux Kernel OOM Killer(Exit Code 137 / SIGKILL)가 발생하지 않고 상시 안정 구동된다.

**Why this priority**: 사용자가 요구한 64K 풀 컨텍스트를 품질 저하 없이 충족하면서도 프로세스가 OOM Killer에 의해 불시에 강제 종료되는 시스템 불안정을 완벽히 차단하기 위함이다.

**Independent Test**: 3종 모델이 기동된 상태에서 64K 컨텍스트 추론 및 임베딩/리랭킹 부하를 가했을 때 프로세스 Crash(OOM Kill) 없이 정상 가동이 유지되는지 검증한다.

**Acceptance Scenarios**:

1. **Given** 게이트웨이가 기동될 때, **When** `qwen3.5-2b` 프로세스가 생성되면, **Then** `n_ctx=65536`과 함께 고품질 8비트 KV 캐시 양자화(`--type_k q8_0 --type_v q8_0`) 인자가 적용되어 메모리 사용량이 안전 임계치 이내로 통제되어야 한다.
2. **Given** 3종 모델이 동시 상주하는 환경에서, **When** 연속 추론 요청이 유입되어도, **Then** Kernel OOM Killer에 의한 프로세스 종료(Exit Code 137)가 0건이어야 한다.

---

### User Story 3 - GPU 리랭커 복구 및 실패 시 무중단 안전 폴백 보장 (Priority: P3)

RAG 파이프라인이 ChromaDB/MySQL 1차 검색 결과에 대해 2차 정밀 리랭킹을 수행할 때, 게이트웨이의 GPU 리랭커(`bge-reranker-v2-m3` @ 8091)가 정상 점수를 산출하고, 일시적 네트워크 타임아웃이나 미가용 시에도 `NoneType` 크래시 없이 1차 유사도 기반 순위로 안전 폴백(Safe Fallback)하여 끊김 없이 서빙한다.

**Why this priority**: 리랭커 반환값 누락 시 `TypeError: 'NoneType' object is not iterable`로 파이프라인 전체가 크래시되어 0건으로 빠지는 취약점을 원천 차단하여 시스템 견고성을 보장한다.

**Independent Test**: 리랭커 엔드포인트를 모의 차단한 상태에서도 `BGEReranker.rerank()`가 크래시 없이 1차 검색 순위와 점수를 반환하며 파이프라인이 정상 완주되는지 검증한다.

**Acceptance Scenarios**:

1. **Given** 모델 게이트웨이 8091 포트가 활성화된 상태에서, **When** `AiGatewayClient.rerank()`가 호출되면, **Then** 정상적인 5건의 정밀 재순위화 점수가 반환되어야 한다.
2. **Given** 리랭커 호출이 실패하여 `None`이 반환되는 극단적 상황에서, **When** `BGEReranker.rerank()`가 실행되면, **Then** 예외 발생 없이 1차 유사도 순위(Fallback used: True)로 완주되어 정상 답변이 생성되어야 한다.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 `bteam/oliview_core/db.py` (및 A/B 챗봇 하위 모듈)의 `fetch_review_metadata` SQL 쿼리를 실제 MySQL 스키마(`vw_chroma_review_sentences` 뷰)와 완벽 일치하도록 수정하여, `Unknown column 'p.brand'` 에러 없이 정확한 제품명, 브랜드명, 리뷰 내용을 반환해야 한다.
- **FR-002**: 시스템은 `bteam/oliview_core/rerank.py`의 `BGEReranker.rerank()`에서 `client.rerank()` 결과가 `None`인 경우를 명시적으로 방어하여, `TypeError: 'NoneType'` 크래시 없이 1차 검색 순위로 안전하게 Fallback되도록 보장해야 한다.
- **FR-003**: 시스템은 `model_gateway/src/core/process_manager.py`의 `build_server_command`에서 `n_ctx >= 32768`인 고용량 컨텍스트 모델 로드 시 q8_0 KV 캐시 양자화 인자(`--type_k q8_0 --type_v q8_0`)를 주입하여 64K 컨텍스트 유지 상태에서의 Kernel OOM Killer(Exit 137)를 원천 차단해야 한다.
- **FR-004**: 시스템은 `model_gateway/src/core/auxiliary_manager.py`의 `check_and_recover_crashes()` 감시 조건을 개선하여, 상태가 `UNLOADED` 또는 `ERROR`이거나 포트 소켓이 닫혀 있을 때도 자동으로 `ensure_rerank_resident()` 및 `ensure_embedding_resident()`를 트리거하여 자가치유를 수행해야 한다.
- **FR-005**: 시스템은 `bteam/Oliview_chatbot_a`, `bteam/Oliview_chatbot_b` 및 통합 `bteam/oliview_core` 전반에 걸쳐 수정된 모듈이 일관되게 동기화되도록 보장해야 한다.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 올리뷰 챗봇 A 및 B UI에서 대표 질의 실행 시 0건 부재 고지 없이 100% 정상 분석 답변 및 인라인 인용이 출력된다.
- **SC-002**: `fetch_review_metadata`의 SQL 쿼리 성공률 100% (SQL 에러 0건) 및 메타데이터 반환 건수 > 0건.
- **SC-003**: 64K 컨텍스트 서빙 상태에서 Kernel OOM Killer 강제 종료(Exit 137) 발생 0건.
- **SC-004**: 리랭커 실패 시뮬레이션 시 파이프라인 무중단 완료율 100% (크래시 0건).
- **SC-005**: 게이트웨이 포트 8081, 8089, 8090, 8091 4종 포트 상시 가용성 유지.
