# Feature Specification: 016-system-codebase-refactoring (통합 시스템 코드베이스 리팩토링 및 아키텍처 현대화)

**Feature Branch**: `016-system-codebase-refactoring`

**Created**: 2026-08-19

**Status**: Clarified & Validated

**Input**: User description: "리펙토링 작업을 위한 리서치를 진행하고, 스펙 작성"

---

## 1. 개요 및 배경 (Overview & Background)

AISERVICE 생태계(PILOS 시장 수급 분석, Oliview 뷰티 리뷰 분석 올리챗 A & 올원챗 B, vLLM 모델 게이트웨이)는 급격한 기능 추가와 서비스 안정화 과정을 거치며 성능과 편의성이 대폭 향상되었습니다. 

그러나 초기 교육용 프로토타입 스크립트(`01.xxx`, `02.xxx`, `03.03.xxx`, `04.xxx`, `05.xxx`, `06.xxx`), 동적 모듈 로더 체이닝(`importlib` 기반 파일 동적 임포트), 서브시스템 간 중복 코드(URL 인코딩, 텍스트 정제, DB 연결 풀, 원격 모델 호출 클라이언트), 불일치하는 환경변수 명명 체계 등 **코드베이스 유지보수성 저하 및 구조적 부채(Technical Debt)**가 누적되어 있습니다.

본 명세서는 서비스 무중단성과 기존 사용자 경험(UI/UX, 4단계 시각화, 고속 GPU 온로드 추론 속도)을 100% 보존하면서, 코드베이스를 현대적이고 모듈화된 패키지 구조로 전환하고 중복을 제거하여 **지속 가능한 유지보수성 및 확장성을 확보하기 위한 종합 리팩토링 규격**을 정의합니다.

---

## Clarifications

### Session 2026-08-19
- Q: 올리뷰 챗봇 A의 핵심 파이프라인(01~05)을 표준 패키지로 전환할 때, 패키지 네이밍 및 배치 구조를 어떻게 구성할까요? → A: Option A (`bteam/oliview_core/` 단일 공유 패키지를 신설하여 검색, 리랭킹, LLM 통신, 데이터 정제를 통합하고 챗봇 A, B 및 백엔드가 공통 import)
- Q: 기존 순번 파일(`01~05.01`)을 `oliview_core`로 마이그레이션한 후, 기존 파일들의 처리 방식을 어떻게 결정할까요? → A: Option A (핵심 실행 파일 `06.02.app.py`, `06.app.py`는 `oliview_core`를 호출하는 하위 호환 래퍼로 전환하고, 중복 스크립트는 `legacy_archive/`로 격리 보관)
- Q: 다중 페르소나 심층 분석에서 도출된 4대 방어 조항을 명세서에 즉시 반영할까요? → A: Option A (4대 방어 조항인 컨테이너 PYTHONPATH 규격, 동기/비동기 이중 클라이언트, Streamlit 2단계 파이프라인 계약, 이원화 SLA를 명세서에 공식 반영)

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 개발자 및 운영자의 표준 패키지 기반 유지보수성 개선 (Priority: P1)

시스템을 개발 및 운영하는 엔지니어는 교육용 순번 스크립트 파일(`01.`, `02.`, `05.01.` 등)과 위험한 런타임 동적 임포트 체이닝 대신, 표준화된 모듈/패키지 구조(`bteam/oliview_core/`)를 통해 코드베이스를 탐색하고 기능을 수정/배포할 수 있어야 합니다.

**Why this priority**:
동적 파일 임포트 방식은 IDE 정적 분석(Linter, 타입 힌트, 심볼 참조)을 방해하고 런타임 모듈 네임스페이스 누락(`@dataclass` 오류 등)을 유발하는 시스템 불안정의 핵심 원인입니다. 이를 표준 구조로 전환하는 것이 가장 시급합니다.

**Independent Test**:
- 표준 모듈 경로(`import oliview_core...`)를 통해 검색, 리랭킹, 챗봇 파이프라인이 임의의 환경에서 동적 파일 로더 없이 즉시 실행 및 단위 테스트될 수 있습니다.

**Acceptance Scenarios**:
1. **Given** 챗봇 서비스가 구동될 때, **When** 핵심 모듈이 로드되면, **Then** 하드코딩된 파일 경로가 아닌 표준 패키지 임포트를 통해 모든 컴포넌트(임베딩, 벡터스토어, BM25, 필터, 리랭커, LLM)가 오류 없이 즉시 인스턴스화된다.
2. **Given** 개발자가 코드를 수정할 때, **When** IDE 및 정적 분석 도구를 실행하면, **Then** 모든 클래스, 함수, 타입 힌트가 단일 소스에서 정확히 참조된다.

---

### User Story 2 - 공통 RAG 클라이언트 및 통신 인터페이스 표준화 (Priority: P1)

A팀(PILOS)과 B팀(Oliview ChatA, ChatB)의 서비스가 모델 서빙 게이트웨이(LLM, BGE-M3 임베딩, BGE-Reranker)와 통신할 때, 각자 파편화되어 작성된 HTTP 클라이언트 코드를 하나의 견고한 **공통 AI 클라이언트 모듈**로 통합하여 관리합니다.

**Why this priority**:
모델 통신 시 타임아웃, 커넥션 풀 누수, 에러 시 복구(Fallback), 응답 벡터 차원(2D/1D) 정규화 로직이 서비스별로 중복 작성되어 장애 발생 시 중복 수정이 필요합니다.

**Independent Test**:
- 공통 AI 클라이언트 라이브러리를 통해 A팀과 B팀 서비스 모두에서 0.05초 이내의 임베딩/리랭킹 응답 및 무중단 토큰 스트리밍을 정상 수신함을 검증합니다.

**Acceptance Scenarios**:
1. **Given** 챗봇 요청이 유입될 때, **When** 임베딩 또는 리랭킹을 호출하면, **Then** 공통 커넥션 풀을 활용하여 불필요한 TCP 핸드셰이크 없이 최소 지연 시간으로 결과를 반환받는다.
2. **Given** 모델 서버에 일시적 지연이나 장애가 발생할 때, **When** 공통 클라이언트가 이를 감지하면, **Then** 사전에 정의된 타임아웃 및 표준 Fallback 메커니즘을 일관되게 적용하여 사용자 화면에 안전한 대체 추천을 제공한다.

---

### User Story 3 - 중복 코드 제거 및 단일 소스 원칙(SSOT) 확립 (Priority: P2)

기존 프로젝트에 산재한 중복 파일(`06.app.py` vs `06.02.app.py`, `05.chatbot.py` vs `05.01.chatbot_list_memory.py`), 중복 유틸리티 함수(올리브영 URL 생성, 텍스트 노이즈 정제, 감성 레이블 정규화, MySQL 연결 관리)를 `oliview_core` 공통 도메인 유틸리티로 통합하고, 기존 중복 스크립트는 `legacy_archive/`로 안전하게 격리합니다.

**Why this priority**:
동일한 기능의 코드가 여러 파일에 분산되어 있으면 한 곳을 수정해도 다른 파일에 버그가 잔존하는 회귀 현상이 발생합니다.

**Independent Test**:
- 중복 파일이 단일 엔트리포인트로 정리된 후에도 올리챗 A(`chata`), 올원챗 B(`chatb`), PILOS(`ateam/pilos`)가 기존과 완전히 동일한 UI/UX 및 분석 결과를 산출합니다.

**Acceptance Scenarios**:
1. **Given** 서비스가 실행 중일 때, **When** 상품 리뷰 정제나 외부 링크 생성을 수행하면, **Then** 통합 유틸리티 함수를 단일 호출하여 동일한 품질의 정제 결과를 얻는다.
2. **Given** 레거시 스크립트들이 `legacy_archive/`로 이동할 때, **When** 전체 회귀 테스트를 수행하면, **Then** 모든 챗봇 실행 및 단위 테스트가 100% 정상 통과한다.

---

### User Story 4 - 환경설정 명명 규칙 및 구성 관리 일원화 (Priority: P3)

컨테이너 및 로컬 개발 환경에서 사용하는 환경변수(`SERVER_HOST`, `MAIN_PORT`, `LLM_BASE_URL`, `EMBED_PORT`, `EMBEDDING_BASE_URL`, `RERANK_PORT`, `RERANK_BASE_URL` 등)의 명명 규칙을 표준화하고 단일 설정 로더(Config Manager)로 관리합니다.

**Why this priority**:
서비스마다 포트와 호스트를 조합하는 방식이 달라 배포 및 포트 변경 시 누락이 발생하기 쉽습니다.

**Independent Test**:
- 통합 설정 로더를 통해 로컬/도커 환경에 구애받지 않고 일관되게 엔드포인트 URL과 데이터베이스 접속 정보가 해석됨을 검증합니다.

**Acceptance Scenarios**:
1. **Given** 도커 컨테이너가 배포될 때, **When** 표준 환경 변수가 주입되면, **Then** 모든 서브시스템이 동일한 규칙으로 게이트웨이 주소를 해석하여 통신한다.

---

### Edge Cases

- **레거시 참조 호환성 유지**: 외부 스크립트나 도커파일이 과거 파일명(`06.02.app.py`, `06.app.py`, `05.chatbot.py` 등)을 직접 진입점으로 호출하더라도 래퍼(Shim/Alias)를 통해 하위 호환성을 완벽히 보장해야 함.
- **VRAM 상시 상주 프로세스 충돌 방지**: 리팩토링 과정에서 모델 게이트웨이의 GPU 프로세스(`8089`, `8090`, `8091`)가 중복 실행되거나 VRAM 누수가 발생하지 않아야 함.
- **스트리밍 도중 네트워크 단절**: 마크다운 파서 및 SSE 스트림 소비자가 불완전한 패킷을 수신하더라도 브라우저 무한 루프나 프리징 없이 안전하게 복구되어야 함.

---

## 3. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 기존의 순번 기반 스크립트 체이닝 방식을 제거하고 `bteam/oliview_core/` 단일 공유 패키지 구조로 완전히 리팩토링되어야 한다.
- **FR-002**: 챗봇 A의 진입점(`app.py`)과 핵심 파이프라인(`service.py` / `pipeline.py`)은 단일 표준 엔트리로 통합 관리되어야 하며, `06.02.app.py`와 `06.app.py`는 신규 모듈을 호출하는 하위 호환 래퍼(Shim)로 전환되고 레거시 중간 스크립트(`01~05.01`)는 `legacy_archive/` 디렉토리로 격리 보존되어야 한다.
- **FR-003**: 챗봇 A와 챗봇 B 간의 중복 비즈니스 로직(URL 생성, 텍스트 정제, 감성 매핑, RAG 단계별 메타데이터 스키마)은 `oliview_core` 공유 도메인 모듈로 단일화되어야 한다.
- **FR-004**: 시스템은 통합 AI 모델 게이트웨이(`vllm-serv-gateway:8081`, `8090`, `8091`)와의 통신을 전담하는 공통 HTTP 클라이언트 모듈(비동기 커넥션 풀, 타임아웃, 예외 처리 일원화)을 제공해야 한다.
- **FR-005**: 리팩토링 후에도 사용자에게 제공되는 4단계 실시간 상태창(`st.status`), 실시간 토큰 스트리밍, 원문 리뷰 아코디언, 카테고리 칩 및 검색 속도(1~3단계 150ms 이내)는 완벽히 동일하게 유지되어야 한다.
- **FR-006**: PILOS 웹 챗봇의 마크다운 렌더러는 스트리밍 시 미완성 토큰이 들어오더라도 브라우저 메인 스레드 무한 루프가 발생하지 않도록 안전 가드가 항시 유지되어야 한다.
- **FR-007**: 모든 모듈은 명확한 타입 어노테이션과 Pydantic/Dataclass 기반의 데이터 계약(Schema)을 준수해야 한다.
- **FR-008**: 전체 시스템 아키텍처에 대한 자동화된 단위/통합 회귀 테스트 스위트를 완비하여 리팩토링 전후의 기능 일관성을 보증해야 한다.
- **FR-009**: 컨테이너 런타임 및 Docker 마운트 환경에서 `bteam/oliview_core`를 안정적으로 참조할 수 있도록 `PYTHONPATH` 환경변수 규격 및 모듈 임포트 경로 무결성을 보장해야 한다.
- **FR-010**: `AiGatewayClient`는 Streamlit(동기 멀티스레드)과 FastAPI(비동기 이벤트 루프) 환경 모두에서 이벤트 루프 충돌 없이 안전하게 동작하도록 동기(`sync`) 및 비동기(`async`) 인터페이스를 명확히 분리하여 제공해야 한다.
- **FR-011**: `oliview_core.pipeline`은 1~3단계(의도분석, 하이브리드 검색, BGE 리랭킹)를 동기 처리하는 준비 인터페이스(`prepare_pipeline_stream`)와 4단계 LLM 토큰 스트리밍 인터페이스(`generate_answer_stream`)를 명확히 분리하여 제공함으로써 `st.status` 컨테이너의 실시간 시각화 라이프사이클 무결성을 보장해야 한다.
- **FR-012**: 챗봇 A의 '질문 예시 (1클릭 실행)' 영역은 텍스트 길이에 구애받지 않고 글자가 박스 바깥으로 삐져나가지 않도록 컬럼 비율([1.6, 1.4]) 및 버튼 CSS(자동 줄바꿈 `white-space: normal`, `word-break: keep-all`, 동적 높이)가 최적화되어야 한다.

---

### Key Entities

- **RagExecutionMetadata**: RAG 검색 및 리랭킹 파이프라인의 소요 시간, 참조 문서 수, 모델명, 폴백 여부, 원문 리뷰 목록을 담는 통합 실행 데이터 모델.
- **AiGatewayClient**: vLLM 게이트웨이의 LLM 추론, BGE-M3 임베딩, BGE-Reranker 리랭킹 엔드포인트를 표준화하여 호출하는 공통 클라이언트.
- **StepCallbackProtocol**: Streamlit, FastAPI SSE, Flask 웹소켓 등 다양한 프론트엔드에 4단계 진행 상태(`INTENT_ANALYSIS`, `HYBRID_SEARCH`, `RERANKING`, `LLM_SYNTHESIS`)를 통지하는 표준 콜백 인터페이스.
- **DomainSanitizer**: 상품명 매칭, 노이즈 정제, URL 생성, 감성 레이블 정규화를 담당하는 통합 유틸리티.

---

## 4. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: **동적 모듈 로더 제거율 100%** - `importlib.util.spec_from_file_location` 기반의 취약한 파일 동적 임포트가 완전히 제거되고 `oliview_core` 표준 `import` 문으로 전환된다.
- **SC-002**: **코드 중복률 대폭 감소** - 중복 복사된 레거시 스크립트 파일(`06.app.py`, `05.01...`)을 제거하고 통합하여 유지보수 대상 코드 라인 수를 30% 이상 경량화한다.
- **SC-003**: **사용자 체감 성능 및 기능 무결성 100% 보존** - GPU 가속 시 검색 1~3단계 지연 150ms 이내 및 최초 토큰 200ms 이내 응답을 달성하며, 게이트웨이 장애 시 로컬 Fallback으로 Graceful Degradation되어 3초 이내에 안전하게 대체 추천을 생성한다.
- **SC-004**: **자동화 테스트 커버리지 강화** - 핵심 검색/리랭킹/스트리밍/에러복구 기능에 대한 단위 및 통합 테스트가 100% 통과하여 회귀 버그 발생 확률을 0에 수렴하도록 한다.

---

## 5. Assumptions

- **A-001**: 모델 서빙 게이트웨이의 GPU 상시 온로드 구성(Port 8081, 8089, 8090, 8091)은 현재 설정대로 최우선 보존되며 리팩토링 대상에서 제외된다.
- **A-002**: 데이터베이스(MySQL `bteam_db`, `pilos-db`)의 테이블 스키마 및 적재된 데이터는 변경 없이 그대로 보존된다.
- **A-003**: 기존 Nginx 게이트웨이(`/bteam/chata/`, `/bteam/chatb/`, `/ateam/pilos/` 등)의 라우팅 경로는 변경되지 않고 동일한 엔드포인트를 유지한다.
