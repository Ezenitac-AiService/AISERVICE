# Feature Specification: Audit & Hardening of Dynamic Configs and OOM Prevention

**Feature Branch**: `034-audit-config-oom-guards`  
**Created**: 2026-08-26  
**Status**: Draft  
**Input**: User description: "방금 케이스 같은 부분이 분명히 또 있을거야 이번 리펙토링 주제는 방금의 이슈를 중점으로 검토해서 스펙을 작성하자, 1. 하드코딩 되어있는 부분은 없는가? 2. 환경변수나, 벤치마킹등으로 설정된 설정값이 로직중에 덮어씌워지거나 무시되는 부분이 있는가? 3. 기타 oom을 유발할만한 요인이 있는가?"

---

## 1. 개요 및 배경 (Context & Problem Statement)

### 1.1 현상 및 배경 (Background)
이전 세션에서 게이트웨이가 2B 단일 상주 모드로 전환되었음에도 불구하고, 클라이언트 환경변수 및 코드 내부의 과거 레거시 하드코딩(`qwen3.5-4b`), 함수 기본 인자(`n_ctx=4096`)에 의한 설정값 덮어쓰기, 프로세스 로딩 중 인터럽트 킬로 인한 재시작 루프 등의 잠재 결함이 발견되었습니다.  
이러한 문제는 8GB GPU 환경에서 메모리 낭비, 불필요한 모델 스와핑, 타임아웃, 예기치 않은 OOM 크래시를 유발할 수 있습니다.

### 1.2 3대 전수 점검 및 리팩토링 목표 (3 Core Pillars)
1. **하드코딩 전수 제거 (Zero Hardcoding)**:
   - 모델명, 포트 번호, VRAM 용량, 컨텍스트 크기 등 시스템 전반에 산재한 레거시 문자열/숫자 하드코딩을 단일 진실 소스([server_config.json](file:///c:/AISERVICE/model_gateway/config/server_config.json), [model_context_profiles.json](file:///c:/AISERVICE/model_gateway/config/model_context_profiles.json), `.env`)로 완전 일원화합니다.
2. **설정값 덮어쓰기 및 무시 방지 (Strict Config Hierarchy & No Shadowing)**:
   - `런타임 요청 > 환경변수 > server_config.json > model_config.json > 코드 안전 기본값` 순의 엄격한 설정 우선순위 계층을 확립하여, 함수 기본 인자나 하위 모듈이 상위 설정을 임의로 무시하거나 덮어쓰지 못하도록 방어합니다.
3. **OOM 유발 요인 원천 차단 (Comprehensive OOM & Resource Leak Defense)**:
   - 동시 추론 슬롯 제어, 로딩 상태 중복 킬 방지, 16K 대용량 컨텍스트 슬롯 메모리 안전성, 좀비 프로세스 VRAM 누수 방지 등 OOM을 유발하는 모든 잠재 요인을 원천 격리합니다.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 전사 설정 단일 진실 소스화 및 하드코딩 제거 (Priority: P1)

시스템 운영자 및 개발자는 모델 게이트웨이와 챗봇, 데이터 파이프라인 전반에서 하드코딩된 모델명이나 매직 넘버 없이, 중앙화된 설정 파일과 환경변수만으로 모든 서빙 파라미터를 일관되게 제어할 수 있습니다.

**Why this priority**: 코드 내부에 잔존하는 하드코딩 문자열(예: `qwen3.5-4b` fallback)로 인한 예기치 않은 오작동과 불일치를 원천 방지합니다.

**Independent Test**: 코드베이스 전체에서 레거시 하드코딩 패턴을 정적 분석 스크립트로 검사하고, 설정 파일 변경 시 모든 서비스가 수정된 값을 즉시 참조하는지 검증합니다.

**Acceptance Scenarios**:
1. **Given** `inference_api.py` 및 `llama_manager.py`의 기본값 처리 로직에서, **When** 모델명이나 컨텍스트 크기 fallback을 조회하면, **Then** 하드코딩된 문자열 대신 `ConfigManager` 및 중앙 설정에서 읽어온 값이 반환된다.
2. **Given** 챗봇 및 데이터 파이프라인(Pilos)이 실행될 때, **When** LLM 모델명을 질의하면, **Then** 하드코딩 없이 동적 모델 탐색 또는 중앙 설정을 따른다.

---

### User Story 2 - 설정 우선순위 계층화 및 덮어쓰기 방어 (Priority: P2)

운영자가 환경변수(`.env`)나 서버 설정([server_config.json](file:///c:/AISERVICE/model_gateway/config/server_config.json))으로 16K 컨텍스트(`n_ctx=16384`)나 단일 상주 모드를 지정했을 때, 하위 함수나 모듈의 기본 매개변수(예: `n_ctx=4096`)가 이를 덮어쓰거나 무시하지 않고 상위 설정을 충실히 보존합니다.

**Why this priority**: 설정 파일에 16K를 지정했음에도 내부 함수 호출 시 4K로 다운그레이드되거나 반대로 과도하게 로드되어 OOM이 발생하는 결함을 차단합니다.

**Independent Test**: 환경변수 및 설정 파일에 `current_n_ctx: 16384`를 설정하고 모든 추론/로드 경로를 호출했을 때, 16384가 변조 없이 전달되는지 단위 테스트로 검증합니다.

**Acceptance Scenarios**:
1. **Given** 상위 설정에 `current_n_ctx: 16384`가 지정되어 있을 때, **When** 클라이언트 요청에 `n_ctx`가 생략되어 전달되면, **Then** 시스템은 코드 기본값(4096)으로 덮어쓰지 않고 상위 설정값(16384)을 그대로 채택한다.

---

### User Story 3 - 동시성 제어 및 OOM 리소스 누수 원천 차단 (Priority: P3)

대량의 배치 작업과 다중 사용자 챗봇 질의가 동시에 유입되거나 모델 재로딩이 발생하는 극한 상황에서도, 시스템은 VRAM 한도 초과(OOM), 프로세스 무한 재시작, 메모리 누수 없이 100% 가동을 유지합니다.

**Why this priority**: 8GB VRAM이라는 물리적 하드웨어 한계 내에서 무중단 가동성과 높은 가용성을 보장합니다.

**Independent Test**: 챗봇 다중 동시 요청과 Pilos 배치 작업을 동시 인입하여, VRAM 피크 점유량이 안전 한도(5,000MB) 이내로 유지되고 OOM 크래시가 0건인지 부하 테스트로 검증합니다.

**Acceptance Scenarios**:
1. **Given** 모델이 로딩 중(`LOADING` 상태)일 때, **When** 새로운 추론 요청이 유입되면, **Then** 시스템은 기존 로딩 프로세스를 킬하지 않고 완료 대기 후 안전하게 서빙한다.
2. **Given** 다중 요청이 유입될 때, **When** GPU 큐와 세마포어가 동작하면, **Then** 동시 실행 수는 VRAM 안전 한도 내로 제어되고 초과 요청은 큐에서 안전하게 대기한다.

---

## 3. 요구사항 (Requirements) *(mandatory)*

### Functional Requirements

- **FR-001 (하드코딩 전수 점검 및 제거)**: `model_gateway`, `bteam/oliview_core`, `pilos` 전반의 소스코드에서 하드코딩된 레거시 모델명(`qwen3.5-4b` fallback 등), 포트 번호, VRAM 용량 매직 넘버를 `ConfigManager` 및 중앙 설정으로 교체해야 한다.
- **FR-002 (엄격한 설정 계층화)**: 설정 해석 우선순위를 `[1] 요청 페이로드 > [2] 환경변수 > [3] server_config.json > [4] model_config.json > [5] 벤치마크 프로파일 > [6] 안전 기본값`으로 명문화하고 하위 계층에 의한 덮어쓰기를 엄격히 금지해야 한다.
- **FR-003 (컨텍스트 윈도우 일관성 보장)**: 모든 `n_ctx` 처리 로직에서 요청에 명시되지 않은 경우 임의의 축소값(4096)이 아닌 중앙 설정의 대용량 컨텍스트(16384)를 기본값으로 일관되게 주입해야 한다.
- **FR-004 (로딩 프로세스 보호)**: `llama_manager.py`는 `LOADING` 상태의 프로세스가 있을 때 중복 로드 요청이 들어오더라도 프로세스를 강제 종료(Cascade Kill)하지 않고 준비 완료를 대기(`_wait_for_ready`)해야 한다.
- **FR-005 (VRAM 안전 상한선 준수)**: `process_manager.py`의 프리플라이트 VRAM 검사기(`calculate_base_vram_mb`)는 GQA 및 FlashAttention 기반 KV 캐시 크기를 정확히 반영하여 허위 OOM 거절을 방지해야 한다.
- **FR-006 (동시성 세마포어 및 공정 큐 제어)**: GPU 메모리 초과를 방지하기 위해 게이트웨이 레벨의 `AsyncFairQueue`와 클라이언트 레벨의 `_gpu_semaphore(max=3)`가 상호 연동되어 동시 추론 폭주를 방어해야 한다.
- **FR-007 (좀비 프로세스 및 포트 충돌 방어)**: 서빙 프로세스 시작 전 이전 프로세스의 완전 종료 및 VRAM 해제를 비동기로 검증하고, 포트 점유 충돌을 사전에 회피해야 한다.
- **FR-008 (인메모리 캐시 메모리 상한 관리)**: Redis 및 클라이언트 인메모리 캐시(L1~L5)는 TTL 만료 및 LRU 축출 정책을 엄격히 적용하여 무제한 메모리 증식을 차단해야 한다.

---

## 4. Success Criteria *(mandatory)*

1. **하드코딩 잔재 0건**: 정적 코드 분석 및 전수 검색 결과 레거시 모델명/포트 하드코딩 발생 건수 **0건**.
2. **설정값 보존율 100%**: 상위 설정(`16384 ctx`, `qwen3.5-2b`)이 내부 함수 매개변수나 하위 로직에 의해 변조되거나 덮어씌워지는 현상 **0건**.
3. **극한 상황 OOM 발생 0건**: 동시 요청 및 배치 작업 병행 시 Linux Kernel OOM Killer(Exit 137) 또는 CUDA OOM 발생 **0건**.
4. **회귀 테스트 무결점**: 전사 5대 종합 회귀 테스트 스위트 100% 통과 유지.

---

## 5. Configuration Priority & Audit Map

```text
[Configuration Priority Stack]
  Level 1: Explicit Request Payload (e.g. {"model": "...", "n_ctx": 16384})
    ↓ (Fallback if None)
  Level 2: Container Environment Variables (.env / docker-compose.yml)
    ↓ (Fallback if None)
  Level 3: Master Server Configuration (model_gateway/config/server_config.json)
    ↓ (Fallback if None)
  Level 4: Dynamic Model State (model_gateway/config/model_config.json)
    ↓ (Fallback if None)
  Level 5: Hardware Benchmark Profile (model_gateway/config/model_context_profiles.json)
    ↓ (Fallback if None)
  Level 6: Safe Global Defaults (qwen3.5-2b, n_ctx=16384)
```
