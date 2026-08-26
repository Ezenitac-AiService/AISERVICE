# Feature Specification: Dynamic Model Discovery & Gateway Config Synchronization

**Feature Branch**: `033-dynamic-model-discovery-sync`  
**Created**: 2026-08-26  
**Status**: Draft  
**Input**: User description: "왜 4b 모델을 호출하지? 하드코딩 되어있어? 지금 모델 게이트웨이 컨테이너는 2b 모델만 서비스하는 셋팅이잖아, 설정 파일의 값을 동적으로 반영하는 내용이 없나? 분석해봐"

---

## 1. 개요 및 배경 (Context & Problem Statement)

### 1.1 현상 분석 (Why 4B was called)
1. **과거 다중 계층 라우팅(Spec 013)의 잔재**:
   - 과거 아키텍처(Spec 013)에서 단순 질의는 `qwen3.5-2b`, RAG 심층 합성은 `qwen3.5-4b`로 분리 호출하도록 설계되었습니다.
   - 이에 따라 루트 `.env`와 `docker-compose.yml`에 `SYNTHESIS_LLM_MODEL=qwen3.5-4b`가 정의되어 컨테이너 환경변수로 주입되었습니다.
2. **클라이언트의 정적 환경변수 의존 (Static Configuration Binding)**:
   - 챗봇 클라이언트([CoreSettings](file:///c:/AISERVICE/bteam/oliview_core/config.py) 및 [AiGatewayClient](file:///c:/AISERVICE/bteam/oliview_core/client.py))는 게이트웨이의 실제 가동 상태나 설정 파일([server_config.json](file:///c:/AISERVICE/model_gateway/config/server_config.json))을 동적으로 확인하지 않고, 컨테이너 환경변수(`SYNTHESIS_LLM_MODEL`)에만 고정적으로 의존했습니다.
3. **게이트웨이 동적 발견(Dynamic Discovery) 부재**:
   - 모델 게이트웨이가 8GB VRAM 최적화를 위해 `qwen3.5-2b` 단일 상주 모드로 전환되었음에도, 클라이언트는 이를 사전에 질의(`GET /v1/models`)하여 활성 모델을 동적으로 획득하는 메커니즘이 없었습니다.

### 1.2 해결 목표 (Goal)
- **동적 모델 탐색(Dynamic Model Discovery)**: 클라이언트가 시작 시점 및 런타임에 게이트웨이의 `GET /v1/models` 엔드포인트를 통해 실제 상주 중인 활성 모델을 동적으로 조회하여 호출 모델명을 자동 동기화합니다.
- **설정 정합성 일원화**: `.env`, `docker-compose.yml`, `server_config.json`의 모델 설정 기본값을 현재 GPU 환경(8GB VRAM)에 최적화된 `qwen3.5-2b`로 통일하고, 향후 고용량 GPU 마이그레이션 시 `server_config.json` 단일 수정만으로 전사 서비스가 자동 적응하도록 개선합니다.
- **게이트웨이 투명 매핑 (Transparent Model Aliasing)**: 단일 상주 모드에서 클라이언트가 구버전 모델명을 요청하더라도 게이트웨이가 프로세스 재시작이나 에러 없이 상주 모델로 투명하게 라우팅합니다.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 클라이언트의 게이트웨이 활성 모델 동적 탐색 (Priority: P1)

챗봇 클라이언트 서비스(A팀/B팀)는 기동 시 및 주기적으로 모델 게이트웨이의 활성 모델 목록을 조회하여, 게이트웨이가 서빙 중인 최적의 기본 LLM 모델명을 동적으로 학습하고 RAG 생성에 사용합니다.

**Why this priority**: 환경변수나 코드 수정 없이 게이트웨이 설정 변경만으로 모든 다운스트림 챗봇이 올바른 모델을 즉시 사용할 수 있도록 보장합니다.

**Independent Test**: 클라이언트 환경변수를 지정하지 않거나 임의의 값을 주더라도, 게이트웨이 `GET /v1/models`에 등록된 활성 모델(`qwen3.5-2b`)로 자동 매핑되어 질의가 성공하는지 검증합니다.

**Acceptance Scenarios**:
1. **Given** 모델 게이트웨이가 `qwen3.5-2b`를 상주 서빙 중일 때, **When** 챗봇 클라이언트가 초기화되면, **Then** 클라이언트는 게이트웨이로부터 활성 모델명(`qwen3.5-2b`)을 획득하여 내부 `synthesis_llm_model`로 자동 설정한다.
2. **Given** 게이트웨이와 일시적인 통신 지연이 발생할 때, **When** 모델 조회가 실패하면, **Then** 클라이언트는 로컬 설정(환경변수 또는 안전 기본값)으로 안전하게 폴백한다.

---

### User Story 2 - 통합 환경 설정 일원화 및 동기화 (Priority: P2)

운영자 및 개발자는 `.env`, `docker-compose.yml`, `server_config.json`의 기본 모델 설정이 상호 모순 없이 일관되게 관리되는 환경을 제공받습니다.

**Why this priority**: 다중 설정 파일 간의 불일치로 인한 예기치 않은 프로세스 킬 및 OOM 충돌을 사전에 차단합니다.

**Independent Test**: `docker-compose up` 실행 시 모든 서비스가 통일된 모델(`qwen3.5-2b`)로 연동되어 오류 없이 기동되는지 확인합니다.

**Acceptance Scenarios**:
1. **Given** 루트 `.env`와 `docker-compose.yml`이 로드될 때, **When** 기본 환경변수를 검사하면, **Then** `FAST_LLM_MODEL`과 `SYNTHESIS_LLM_MODEL`이 `qwen3.5-2b`로 통일되어 있다.
2. **Given** 운영자가 `server_config.json`의 `default_model`을 변경할 때, **When** 게이트웨이를 재시작하면, **Then** 클라이언트가 변경된 모델명을 자동으로 감지한다.

---

### User Story 3 - 비상주/구버전 모델 요청에 대한 투명 라우팅 (Priority: P3)

외부 클라이언트나 테스트 스크립트가 `qwen3.5-4b` 등 비상주 모델명을 명시하여 요청하더라도, 게이트웨이가 프로세스 다운 없이 현재 상주 모델로 자동 변환하여 안정적으로 응답합니다.

**Why this priority**: 레거시 호출 규격 및 외부 클라이언트와의 하위 호환성을 유지하고 서비스 무중단을 보장합니다.

**Independent Test**: `model: "qwen3.5-4b"` 페이로드로 `POST /v1/chat/completions`를 호출했을 때, 500 에러나 프로세스 재시작 없이 200 OK와 스트리밍 응답이 반환되는지 검증합니다.

**Acceptance Scenarios**:
1. **Given** 게이트웨이가 단일 상주 모드일 때, **When** 요청 페이로드에 `model: "qwen3.5-4b"`가 포함되면, **Then** 게이트웨이는 내부적으로 상주 모델(`qwen3.5-2b`)로 요청을 포워딩하여 정상 응답을 반환한다.

---

### Edge Cases
- **게이트웨이 미기동 상태에서 클라이언트 시작**: 게이트웨이가 아직 준비되지 않은 경우 클라이언트는 로컬 기본값(`qwen3.5-2b`)을 사용하고, 백그라운드에서 주기적으로 게이트웨이 동기화를 재시도.
- **다중 모델 카탈로그 응답 파싱**: `GET /v1/models` 응답에서 `owned_by: "me"` 또는 `is_active: true` 필드를 정확히 파싱하여 임베딩/리랭커 모델과 LLM 텍스트 생성 모델을 명확히 구분.

---

## 3. 요구사항 (Requirements) *(mandatory)*

### Functional Requirements

- **FR-001**: 클라이언트 라이브러리(`AiGatewayClient`)는 기동 시 게이트웨이의 `GET /v1/models`를 비동기/동기 질의하여 현재 서빙 가능한 LLM 모델명을 동적으로 확인하는 `discover_active_model()` 메서드를 구현해야 한다.
- **FR-002**: 클라이언트 설정 클래스(`CoreSettings`)는 환경변수가 설정되지 않은 경우 동적으로 발견된 모델명을 기본 합성 모델(`synthesis_llm_model`)로 채택해야 한다.
- **FR-003**: 게이트웨이의 `GET /v1/models` 응답은 현재 상주 중인 기본 모델(`default_model` 또는 `current_model`)에 대해 활성 플래그(`is_active: true`, `is_resident: true`) 메타데이터를 명확히 포함해야 한다.
- **FR-004**: 루트 `.env` 및 `docker-compose.yml`의 `SYNTHESIS_LLM_MODEL` 기본값을 `qwen3.5-2b`로 통일하여 정적 설정 간 모순을 해소해야 한다.
- **FR-005**: 모델 게이트웨이의 `reverse_proxy`는 `SINGLE_MODEL_MODE=true`일 때 요청된 `model` 필드가 비상주 모델이더라도 상주 모델로 안전하게 재매핑하고 `model` 파라미터를 교체하여 전달해야 한다.
- **FR-006**: 동적 모델 탐색 결과는 인메모리에 캐싱(TTL 60초)되어 매 요청마다 불필요한 HTTP 오버헤드를 발생시키지 않아야 한다.
- **FR-007**: 모든 모델 동기화 및 라우팅 이벤트는 구조화된 로그(`logger.info`)로 기록되어 모델 해석 과정을 추적할 수 있어야 한다.

---

## 4. Success Criteria *(mandatory)*

1. **설정 불일치 제거**: 시스템 내 `qwen3.5-4b` 호출로 인한 불필요한 모델 스와핑, OOM 킬, 500 에러 발생 건수 **0건 달성**.
2. **동적 탐색 자동화**: 게이트웨이 `server_config.json`의 기본 모델 변경 시, 클라이언트 재배포나 코드 수정 없이 60초 이내에 클라이언트가 새 모델명을 동적으로 반영.
3. **호환성 보장**: 레거시 `qwen3.5-4b` 요청에 대한 게이트웨이 응답 성공률 **100% (200 OK)** 유지.
4. **회귀 테스트 무결점**: 전사 5대 종합 회귀 테스트 스위트 100% 통과 유지.

---

## 5. Key Entities & Configuration Map

| 구성 요소 | 위치 | 역할 | 최적값 / 동적 반영 방식 |
| :--- | :--- | :--- | :--- |
| **Gateway Config** | `model_gateway/config/server_config.json` | 서빙 모델 및 포트 마스터 설정 | `"default_model": "qwen3.5-2b"`, `"current_n_ctx": 4096` |
| **Gateway API** | `model_gateway/src/api/routes/inference_api.py` | 모델 카탈로그 및 프록시 라우팅 | `GET /v1/models`에 `is_active` 제공 & 비상주 모델 투명 재매핑 |
| **Client Config** | `bteam/oliview_core/config.py` | 챗봇 코어 설정 규격 | `discover_active_model()` 연동 및 `qwen3.5-2b` 안전 기본값 |
| **Client Gateway** | `bteam/oliview_core/client.py` | HTTP LLM 호출 클라이언트 | 모델 동적 탐색 캐시(TTL 60s) 및 RAG 페이로드 조립 |
| **System Env** | `.env`, `docker-compose.yml` | 컨테이너 환경변수 주입 | `SYNTHESIS_LLM_MODEL=qwen3.5-2b` |
