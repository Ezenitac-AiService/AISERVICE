# Feature Specification: 통합 시스템 아키텍처 점검 및 리팩토링 (010-refactor-unified-system-architecture)

**Feature Branch**: `010-refactor-unified-system-architecture`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "llm 서버나 gateway를 건드는건 아니지? 왜 이제는 pilos 챗봇이 llm 호출할때 무한 딜레이지? 아오... 전체 구성도 점검과 리펙토링하는 스펙 작성을 위한 리서치 진행해줘"

---

## Clarifications

### Session 2026-08-18
- Q: Oliview 프론트엔드의 백엔드 API 호출 경로를 `/bteam/oliview/api/`로 전역 보장하고, 스펙에 정규화 요구사항(FR-008)을 반영하시겠습니까? → A: Option A: `apiBaseUrl` 누락 방지 및 전역 기본값(`/bteam/oliview`) 자동 폴백을 적용하고 `spec.md`에 요구사항 추가

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - PILOS 챗봇 및 정본 지식/리포트 질의 시 무지연 응답 (Priority: P1)

사용자가 PILOS 금융 챗봇 웹 UI(`http://localhost:8080/ateam/pilos/`)에서 종목 분석, 정본 지식, 또는 자유 질문을 입력했을 때, 불필요한 무한 딜레이나 정지 현상 없이 신속하고 투명하게 답변을 받아본다.

**Why this priority**:
PILOS는 금융 도메인 핵심 대화형 분석 서비스로, 사용자가 질문 시 먹통(Hang)이나 무한 로딩이 발생하면 서비스 전체의 신뢰도가 훼손되므로 최우선 해결 대상이다.

**Independent Test**:
PILOS 웹 인터페이스에서 종목 분석 및 정본 지식 질의를 수행하여, 캐시된 데이터는 즉시(< 50ms) 반환되고 동적 LLM 분석은 실시간 스트리밍으로 지연 없이 출력되는지 검증한다.

**Acceptance Scenarios**:
1. **Given** PILOS 챗봇 화면이 열려 있을 때, **When** 사용자가 "PILOS 분석 결과 해석 방법"과 같은 서비스 지식 질문을 전송하면, **Then** 100ms 이내에 즉시 정확한 정본 지식 답변이 표시된다.
2. **Given** 단일 GPU에서 다른 서비스 질의가 처리 중일 때, **When** 사용자가 신규 종목 분석 질문을 전송하면, **Then** 무한 정지되지 않고 대기 상태 안내 후 순차적으로 15초 이내에 스트리밍 답변이 완료된다.

---

### User Story 2 - 3대 챗봇(PILOS, 올리챗, 올원챗) 동시성 격리 및 핫스왑 병목 제거 (Priority: P2)

단일 GPU(8GB VRAM) 환경에서 PILOS, 올리챗(B-Team Streamlit), 올원챗(B-Team FastAPI)이 상호 간섭 없이 공용 AI 모델 게이트웨이를 통해 안정적으로 추론을 수행한다.

**Why this priority**:
서로 다른 챗봇 서비스가 각기 다른 모델 이름을 호출하여 VRAM에서 모델을 계속 교체(Hot-swap)하는 병목(20~30초)을 제거해야 전체 시스템의 처리량이 극대화된다.

**Independent Test**:
3개 챗봇에 동시에 서로 다른 질문을 요청하고, 모델 재로딩(Hot-swap) 없이 단일 상주 모델(`qwen3.5-4b`)을 통해 큐잉 순서대로 순차 완료되는지 검증한다.

**Acceptance Scenarios**:
1. **Given** 올원챗(FastAPI)과 올리챗(Streamlit)과 PILOS가 구동 중일 때, **When** 3개 서비스가 동시에 모델 게이트웨이에 질의하면, **Then** 모델 스왑(VRAM Unload/Reload) 없이 연속 추론이 진행되어 모든 요청이 정상 응답(200 OK)을 수신한다.

---

### User Story 3 - 통합 Nginx 역방향 프록시 및 백엔드 워커 동시성 안정화 (Priority: P3)

사용자가 단일 통합 포털(`http://localhost:8080`)을 통해 PILOS 대시보드, 올리챗, 올원챗, 올리뷰 포털을 탐색하고 상호작용할 때 세션 끊김이나 프록시 타임아웃, 경로 오반출 없이 매끄러운 UX를 경험한다.

**Why this priority**:
Gunicorn 동기 워커 블로킹, 프록시 버퍼링, 및 서브도메인 간 API 경로 충돌을 해결하여 다중 사용자 접속 시 웹 화면과 API가 정확히 상호작용하도록 보장한다.

**Independent Test**:
Nginx 게이트웨이를 통해 장시간 지속되는 SSE 스트리밍 연결과 동시 API 호출, 그리고 Oliview 내 브랜드 상품 클릭 시 상세 페이지 데이터 렌더링을 검증한다.

**Acceptance Scenarios**:
1. **Given** 장시간 스트리밍 답변이 진행되는 도중, **When** 사용자가 다른 페이지 탭을 열거나 추가 API를 호출하면, **Then** 기존 연결이 차단되지 않고 새 요청도 즉시 응답을 받는다.
2. **Given** Oliview 메인 웹(`http://localhost:8080/bteam/oliview/`)에 로그인한 사용자가 내 브랜드 상품 목록에서 특정 상품을 클릭했을 때, **When** 상세 페이지로 이동하면, **Then** A-Team 경로(`/api/`)로 잘못 라우팅되지 않고 올바른 상품 정보, 옵션, 및 감성 분석 리포트가 즉시 정상 표시된다.

---

## Edge Cases

- **GPU VRAM 포화 및 일시적 큐 누적**: 여러 사용자가 동시에 4096 토큰의 장문 생성을 요청할 경우 큐에서 타임아웃 없이 순차 처리되고 클라이언트에 적절한 대기 상태가 안내되는가?
- **외부 LLM 서버 일시 불능**: 모델 서빙 프로세스가 재시작 중일 때 챗봇 UI가 무한 로딩에 빠지지 않고 사용자 친화적인 재시도 안내를 표시하는가?
- **브라우저 탭 조기 종료**: 사용자가 스트리밍 생성 도중 브라우저 탭을 닫거나 취소했을 때, 백엔드 GPU 연산 및 프록시 연결이 즉시 안전하게 정리되는가?
- **프론트엔드 환경변수 미제공 환경**: `apiBaseUrl` 속성이 누락되거나 빈 문자열로 전달되어도 전역 폴백(`/bteam/oliview`)을 통해 올바른 백엔드 API에 도달하는가?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 통합 AI 모델 게이트웨이의 메인 LLM 서빙을 단일 표준 모델(`qwen3.5-4b`)로 고정하여 런타임 모델 핫스왑으로 인한 VRAM 재로딩 지연을 원천 제거해야 한다.
- **FR-002**: 모델 게이트웨이는 단일 GPU 자원 보호를 위한 FIFO 순차 큐를 제공하며, 스트리밍 클라이언트에는 대기 킵얼라이브 상태를, 비스트리밍 클라이언트에는 소켓 타임아웃 방지 킵얼라이브를 보장해야 한다.
- **FR-003**: A-Team PILOS 웹 서버(`pilos-web`)는 Gunicorn 워커 프로파일을 최적화(스레드/비동기 친화적)하여 SSE 스트리밍 중에도 웹 대시보드 및 타 API 요청이 블로킹되지 않아야 한다.
- **FR-004**: B-Team 올원챗(`Oliview_chatbot_b`)은 메인 LLM 호출 모델명을 `qwen3.5-4b`로 통일하여 서브도메인 간 모델 충돌을 방지해야 한다.
- **FR-005**: 3대 챗봇(PILOS, 올리챗, 올원챗)은 OpenAI 호환 표준 API 규격(`POST /v1/chat/completions`, `POST /v1/embeddings`)을 준수하며 게이트웨이 내부 비표준 의존성을 제거해야 한다.
- **FR-006**: 통합 Nginx 게이트웨이(`gateway/nginx.conf`)는 모든 서브도메인 라우트에 대해 SSE 스트리밍 버퍼링 해제(`proxy_buffering off`)와 300초 타임아웃을 일관되게 보장해야 한다.
- **FR-007**: 시스템은 3대 챗봇의 동시성 격리, 지연 시간, 및 데이터 무결성을 검증하는 통합 자동화 회귀 테스트 스위트를 상시 유지해야 한다.
- **FR-008**: B-Team Oliview 프론트엔드는 모든 페이지 및 컴포넌트(`MyBrandpage.jsx`, `BaseProductDetail.jsx`, `ProductDetailPage.jsx`, `CompetitorProductDetailPage.jsx` 등)에서 API 기본 경로를 `/bteam/oliview`로 전역 보장하여 상품 상세, 분석 리포트, 리뷰 상세 조회 시 타 도메인(`/api/`)과의 경로 충돌을 방지하고 정상 데이터를 렌더링해야 한다.

---

### Key Entities

- **통합 모델 게이트웨이 (Model Gateway / Port 8081, 8090, 8091)**: 단일 GPU 상에서 Qwen LLM, BGE-M3 임베딩, BGE 리랭커를 격리 서빙하고 표준 OpenAI 호환 인터페이스를 제공하는 중앙 인프라 엔티티.
- **PILOS 금융 챗봇 서비스 (A-Team PILOS / Port 5000)**: 뉴스 감정 지수 및 종목 분석 리포트 캐시 기반 초고속 응답과 실시간 RAG 스트리밍을 제공하는 금융 분석 엔티티.
- **올리뷰 리뷰 챗봇 A (B-Team OllyChat / Port 8501)**: 57,435건 올리브영 리뷰 인덱스 기반 하이브리드 RAG 및 Streamlit 실시간 토큰 타이핑을 제공하는 뷰티 분석 엔티티.
- **올원챗 맞춤 챗봇 B (B-Team AllOneChat / Port 8002)**: 올리브영 상품 및 사용자 맞춤형 추천/분석을 제공하는 비동기 FastAPI 엔티티.
- **올리뷰 메인 웹 대시보드 (B-Team Oliview / React Vite Port 5173, Flask Port 5050)**: 브랜드 관리자 로그인, 내 브랜드 상품 목록, 상세 분석 리포트, 및 경쟁사 분석을 제공하는 풀스택 엔티티.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: PILOS 정본 지식 및 캐시된 종목 지수 질의 시 응답 시간 **50ms 미만** 달성.
- **SC-002**: 3대 챗봇에서 동적 LLM 분석 질의 시 첫 번째 토큰 출력 시간(TTFT) **2.0초 이내** 진입.
- **SC-003**: 3개 챗봇이 동시에 최대 부하 질의를 요청했을 때 모델 핫스왑 발생 횟수 **0회**, 전 요청 **HTTP 200 성공률 100%** 달성.
- **SC-004**: 통합 회귀 테스트 스위트(`test_multi_chatbot_regression.py`) 전체 테스트 항목 **10초 이내** 100% 통과 유지.
- **SC-005**: Oliview 메인 웹에서 내 브랜드 상품 클릭 시 상품 상세 및 리포트 데이터 로딩 성공률 **100%** 달성.

---

## Assumptions

- 단일 호스트 내에서 NVIDIA GTX 1070 (8GB VRAM) 환경을 전제로 최적화하며, 모델 크기는 4B(Qwen 3.5 4B Q4_K_M)로 VRAM 사용량을 5.5GB 이내로 유지한다.
- A-Team PILOS의 일별 정량 데이터 및 사전 생성 리포트는 MySQL DB(`pilos_v2`)에, B-Team의 리뷰 및 상품 데이터는 `bteam_db`(`oliview_project`)에 각각 독립 정본으로 유지된다.
- Nginx 역방향 프록시(`aiservice-gateway`)는 포트 8080을 통해 모든 웹 트래픽을 중계하며, 서브 컨테이너들의 내부 네트워크 통신은 Docker 브릿지 네트워크(`aiservice-network`)로 격리된다.
