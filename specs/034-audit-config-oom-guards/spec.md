# Feature Specification: Audit, Zero-Hardcoding, and Dual-Strategy OOM Hardening

**Feature Branch**: `034-audit-config-oom-guards`  
**Created**: 2026-08-26  
**Status**: Ready for Planning  
**Input**: User description: "방금 케이스 같은 부분이 분명히 또 있을거야 이번 리펙토링 주제는 방금의 이슈를 중점으로 검토해서 스펙을 작성하자, 1. 하드코딩 되어있는 부분은 없는가? 2. 환경변수나, 벤치마킹등으로 설정된 설정값이 로직중에 덮어씌워지거나 무시되는 부분이 있는가? 3. 기타 oom을 유발할만한 요인이 있는가? 둘다 도입하고 어느 모드를 사용할지 설정하게 하는데, gtx 1070은 FlashAttention 지원이 안되니 gpu 교체시를 위해 구축하고 남기는게 맞아"

---

## 1. 개요 및 배경 (Context & Problem Statement)

### 1.1 현상 및 배경 (Background)
8GB GPU (NVIDIA GTX 1070, Windows OS 점유 ~3.7GB) 환경에서 시스템 메모리 한계(VRAM 8.19GB)를 극복하고 고품질 RAG를 무중단 서빙하기 위해, 코드 내부의 레거시 하드코딩, 설정값 덮어쓰기(Shadowing), OOM 유발 요인을 전수 점검·격리해야 합니다.  
또한, 하드웨어 특성(GTX 1070 Pascal SM 6.1은 FlashAttention 미지원, Q8 KV Cache 지원)을 정확히 반영하고, **"4B(16K) + BGE CPU 오프로드 모드"**와 **"2B(32K) + 에이전틱 하네스 모드"**의 2대 전략을 동적으로 선택할 수 있는 듀얼 서빙 체계를 확립합니다.

---

## 2. 2대 듀얼 서빙 전략 모드 (Dual Serving Strategy Architecture)

운영자는 환경변수(`SERVING_STRATEGY_MODE`) 또는 [server_config.json](file:///c:/AISERVICE/model_gateway/config/server_config.json)을 통해 2가지 모드를 자유롭게 전환할 수 있습니다:

```text
========================================================================================================================
전략 모드                       LLM 상주 (GPU VRAM)          보조 모델 (BGE 임베딩/리랭커)   VRAM 점유     특징 및 강점
========================================================================================================================
[모드 1] MODE_4B_HYBRID_CPU      Qwen 3.5 4B (16K n_ctx)       Host 시스템 RAM (CPU/ONNX)      3.2 GB        4B 고품질 추론 + OOM 0건
[모드 2] MODE_2B_ULTRA_CTX       Qwen 3.5 2B (32K n_ctx)       GPU VRAM (100% Offload)        3.3 GB        32K 초장문 + 에이전틱 루프
========================================================================================================================
* 공통 안전 마진: Windows OS 점유(3.7GB) 합산 시 총 6.9~7.0GB 점유 (8.19GB 한도 내 상시 1.2GB+ 여유 확보)
```

---

## 3. User Scenarios & Testing *(mandatory)*

### User Story 1 - 듀얼 서빙 전략 동적 스위칭 & 4B 16K 무중단 서빙 (Priority: P1) 🎯 MVP

운영자가 `SERVING_STRATEGY_MODE=mode_4b_hybrid_cpu`로 설정하면, 게이트웨이는 BGE 임베딩/리랭커를 CPU로 자동 분기하고 GPU VRAM에 `qwen3.5-4b (16K ctx)`를 안정 상주시킴으로써 8GB VRAM에서도 OOM 크래시 없이 4B 고품질 RAG 답변을 스트리밍한다.

**Why this priority**: 8GB GPU 환경에서 4B 모델과 16K 대용량 컨텍스트를 OOM 없이 완벽 상주 서빙할 수 있는 핵심 솔루션입니다.

**Independent Test**: `SERVING_STRATEGY_MODE=mode_4b_hybrid_cpu`로 기동 후 `POST /v1/chat/completions` (model: 4b) 및 RAG 질의를 실행하여, VRAM 점유가 3.5GB 이하로 유지되고 200 OK 스트리밍이 완료되는지 검증.

**Acceptance Scenarios**:
1. **Given** `SERVING_STRATEGY_MODE=mode_4b_hybrid_cpu`일 때, **When** 시스템이 기동되면, **Then** `bge-m3` 및 `bge-reranker`는 CPU/RAM에서 구동되고 `qwen3.5-4b (16K)`가 GPU에 상주하여 총 VRAM 점유량은 3.5GB 이하를 유지한다.
2. **Given** `SERVING_STRATEGY_MODE=mode_2b_ultra_ctx`일 때, **When** 시스템이 기동되면, **Then** `qwen3.5-2b`가 32K(`n_ctx=32768`) 컨텍스트로 GPU에 상주하고 BGE 모델들도 GPU에 동시 상주한다.

---

### User Story 2 - 전사 하드코딩 전수 제거 및 단일 진실 소스화 (Priority: P2)

게이트웨이, 챗봇 A/B, 데이터 수집 파이프라인(Pilos), 전사 테스트 코드에 산재한 레거시 모델명(`qwen3.5-4b` fallback), 포트 번호, VRAM 매직 넘버를 완전히 제거하고 `ConfigManager`로 일원화한다.

**Why this priority**: 소스코드 곳곳의 하드코딩 잔재로 인한 모순과 예기치 않은 오작동을 근본적으로 차단합니다.

**Independent Test**: 정적 코드 분석 및 전수 검색 스크립트를 실행하여 하드코딩된 레거시 fallback 문자열이 0건인지 검증.

**Acceptance Scenarios**:
1. **Given** `inference_api.py`, `llama_manager.py`, `pilos/`의 모든 모델/포트 처리부에서, **When** 설정을 조회하면, **Then** 코드 내 하드코딩 대신 `ConfigManager` 및 중앙 설정 파일에서 동적으로 값을 읽어온다.
2. **Given** `ateam/` 및 전사 통합/계약 테스트 파일에서, **When** 테스트를 실행하면, **Then** 구버전 정적 어설션 오류 없이 동적 설정값을 기반으로 100% 통과한다.

---

### User Story 3 - 하드웨어 인식 FlashAttention 조건부 활성화 및 Q8 KV 보장 (Priority: P3)

시스템은 기동 시 GPU Compute Capability를 감지하여, GTX 1070(SM 6.1)에서는 지원되지 않는 FlashAttention 옵션을 안전하게 생략/비활성화하고 **Q8_0 KV Cache 양자화**를 활성화하며, 향후 SM >= 8.0 GPU로 교체 시 자동으로 FlashAttention-3을 동적 활성화한다.

**Why this priority**: GTX 1070 환경에서 FlashAttention 명령어 파이프라인 결함으로 인한 비정상 지연이나 경고를 차단하고, 미래 하드웨어 확장을 완벽히 대비합니다.

**Independent Test**: GTX 1070 환경에서 기동 로그를 확인하여 FlashAttention 경고 없이 Q8_0 KV Cache가 적용되는지 검증하고, 모의 SM 8.0 환경에서 FlashAttention이 자동 켜지는지 단위 테스트로 검증.

**Acceptance Scenarios**:
1. **Given** GPU Compute Capability < 8.0 (GTX 1070) 환경일 때, **When** llama-server가 기동되면, **Then** `--flash_attn` 옵션은 생략되고 `--cache-type-k q8_0 --cache-type-v q8_0`가 적용되어 VRAM을 50% 절감한다.
2. **Given** GPU Compute Capability >= 8.0 (RTX 40xx 등) 환경일 때, **When** llama-server가 기동되면, **Then** `--flash_attn True`가 자동으로 추가 인입된다.

---

### User Story 4 - 설정 덮어쓰기(Anti-Shadowing) 방어 및 OOM 리소스 누수 격리 (Priority: P4)

함수 기본 인자(예: `n_ctx=4096`)나 하위 모듈이 상위의 16K/32K 설정을 덮어쓰지 못하도록 엄격히 가드하고, 좀비 프로세스 VRAM 누수 및 동시 추론 폭주를 원천 격리한다.

**Why this priority**: 16K 대용량 컨텍스트의 안정성을 보장하고 극한 상황에서도 OOM 크래시를 0건으로 유지합니다.

**Independent Test**: 다중 동시 추론 및 프로세스 재기동 시 VRAM 누수와 설정 변조가 0건인지 카오스 테스트로 검증.

**Acceptance Scenarios**:
1. **Given** 클라이언트 요청에 `n_ctx`가 생략되었을 때, **When** 추론 파이프라인이 실행되면, **Then** 코드 기본값으로 덮어쓰지 않고 현재 상주 모델의 컨텍스트(16K/32K)를 그대로 보존한다.
2. **Given** 프로세스 종료 요청 시, **When** 프로세스가 중단되면, **Then** 소켓 바인딩 및 PID 종료를 검증하여 좀비 프로세스에 의한 VRAM 중복 점유를 원천 차단한다.

---

## 4. 요구사항 (Requirements) *(mandatory)*

### Functional Requirements

- **FR-001 (듀얼 서빙 전략 모드 지원)**: 시스템은 `SERVING_STRATEGY_MODE` 환경변수를 통해 `mode_4b_hybrid_cpu`(4B GPU + BGE CPU)와 `mode_2b_ultra_ctx`(2B 32K GPU + BGE GPU)를 상호 전환할 수 있어야 한다.
- **FR-002 (하드웨어 인식 FlashAttention & Q8 KV)**: `gpu_detector.py`는 GPU Compute Capability를 감지하여 SM < 8.0(GTX 1070)에서는 FlashAttention을 생략하고 Q8_0 KV Cache를 적용하며, SM >= 8.0에서는 FlashAttention을 자동 활성화해야 한다.
- **FR-003 (하드코딩 전수 점검 및 제거)**: `model_gateway`, `bteam/oliview_core`, `ateam/pilos`, `tests/` 전역에서 하드코딩된 레거시 모델명(`qwen3.5-4b` fallback), 포트 번호, VRAM 매직 넘버를 `ConfigManager`로 교체해야 한다.
- **FR-004 (엄격한 설정 계층화 및 Anti-Shadowing)**: 설정 우선순위를 `[1] 요청 페이로드 > [2] 환경변수 > [3] server_config.json > [4] model_config.json > [5] 벤치마크 프로파일 > [6] 안전 기본값`으로 명문화하고 하위 계층에 의한 덮어쓰기를 엄격히 금지해야 한다.
- **FR-005 (컨텍스트 윈도우 무변조 보장)**: 모든 `n_ctx` 처리 로직에서 요청에 명시되지 않은 경우 임의의 축소값(4096)이 아닌 현재 활성 모드의 컨텍스트(16384 또는 32768)를 일관되게 주입해야 한다.
- **FR-006 (로딩 프로세스 Cascade Kill 방지)**: `llama_manager.py`는 `LOADING` 상태의 프로세스가 있을 때 중복 요청 유입 시 프로세스를 강제 종료하지 않고 완료 대기(`_wait_for_ready`)해야 한다.
- **FR-007 (VRAM 안전 상한선 및 프리플라이트 수식 교정)**: `calculate_base_vram_mb`는 GQA 및 Q8 KV 캐시 수식을 정확히 반영하여 허위 OOM 거절을 방지해야 한다.
- **FR-008 (동시성 세마포어 및 공정 큐 제어)**: `AsyncFairQueue`와 클라이언트 레벨의 `_gpu_semaphore(max=3)`가 연동되어 동시 추론 폭주를 방어해야 한다.
- **FR-009 (좀비 프로세스 소켓 점유 방어)**: 서빙 프로세스 시작 전 이전 프로세스의 소켓 바인딩 해제 및 VRAM 해제를 검증하고, 미종료 프로세스는 `kill -9`로 강제 회수해야 한다.
- **FR-010 (Redis & L5 캐시 메모리 상한 관리)**: Redis 설정에 `maxmemory 512mb` 및 `maxmemory-policy allkeys-lru`를 적용하여 무제한 메모리 팽창을 방어해야 한다.

---

## 5. Success Criteria *(mandatory)*

1. **듀얼 모드 정상 스위칭**: `mode_4b_hybrid_cpu` 및 `mode_2b_ultra_ctx` 전환 시 OOM 0건 및 100% 정상 서빙.
2. **하드코딩 잔재 0건**: 정적 코드 분석 및 전수 검색 결과 레거시 모델명/포트 하드코딩 발생 건수 **0건**.
3. **GTX 1070 최적화**: FlashAttention 경고 0건 및 Q8_0 KV Cache 적용을 통한 50% KV VRAM 절감 실측 확인.
4. **설정값 보존율 100%**: 상위 설정(16K/32K 컨텍스트)이 내부 함수 매개변수에 의해 변조되거나 덮어씌워지는 현상 **0건**.
5. **회귀 테스트 무결점**: 전사 5대 종합 회귀 테스트 스위트 100% 통과 유지.
