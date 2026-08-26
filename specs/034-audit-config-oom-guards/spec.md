# Feature Specification: Audit, Zero-Hardcoding, and Hardware-Tiered OOM Hardening

**Feature Branch**: `034-audit-config-oom-guards`  
**Created**: 2026-08-26  
**Status**: Ready for Planning  
**Input**: User description: "방금 케이스 같은 부분이 분명히 또 있을거야 이번 리펙토링 주제는 방금의 이슈를 중점으로 검토해서 스펙을 작성하자, 1. 하드코딩 되어있는 부분은 없는가? 2. 환경변수나, 벤치마킹등으로 설정된 설정값이 로직중에 덮어씌워지거나 무시되는 부분이 있는가? 3. 기타 oom을 유발할만한 요인이 있는가? 4b 모델을 사용하는 전략은 11gb vram 플렛폼(gtx 1080ti), 12gb vram 플렛폼(rtx 3060)들을 위해서 구축하고, 지금 이 gtx 1070 플렛폼에서는 비활성화 하는 방향으로"

---

## 1. 개요 및 배경 (Context & Problem Statement)

### 1.1 현상 및 배경 (Background)
* **8GB GPU (NVIDIA GTX 1070, Windows OS 점유 ~3.7GB)** 환경에서 시스템 총 VRAM(8.19GB) 한계를 절대 초과하지 않으면서 50ms급 고속 RAG를 제공하기 위해, **BGE 임베딩(0.7GB)과 BGE 리랭커(0.7GB)는 반드시 GPU VRAM에 상주**해야 합니다 (CPU 실행 시 6~10초 지연으로 챗봇 타임아웃 발생).
* 이에 따라 8GB GPU 환경에서는 **2B 모델(16K~32K 컨텍스트) + BGE 2종의 GPU 동시 상주(총 3.3~3.7GB)**를 기본 활성화하고, 다단계 에이전틱 리플렉션 루프(TTC)를 통해 추론 품질을 보완합니다.
* **4B 모델 서빙 전략(4B 16K + BGE 2종 GPU 상주, 총 4.8GB)**은 향후 **11GB (GTX 1080 Ti) 및 12GB (RTX 3060 / 4070)** 플랫폼 마이그레이션을 위해 완전한 코드로 구축하되, **현재 8GB GTX 1070 플랫폼에서는 하드웨어 감지 가드를 통해 자동으로 비활성화(`SINGLE_MODEL_MODE=true`, 4B 요청 시 상주 2B로 투명 라우팅)**합니다.
* 동시에 GTX 1070(Pascal SM 6.1)의 FlashAttention 미지원 특성을 감지하여 안전하게 생략하고, **Q8_0 KV Cache 양자화**를 기본 적용하여 메모리를 최적화합니다.

---

## 2. 하드웨어 VRAM 티어별 서빙 매트릭스 (Hardware-Tiered Serving Topology)

```text
========================================================================================================================
하드웨어 티어                대상 GPU 예시          LLM 서빙 모델         컨텍스트 윈도우    BGE 임베딩/리랭커   총 VRAM 점유 (OS포함)
========================================================================================================================
[Tier 1: 8GB 기본]           GTX 1070 / RTX 2060    Qwen 3.5 2B (Q4_K_M)   16K ~ 32K         GPU VRAM 100%       7.0 ~ 7.4 GB (안전)
                             * 4B 요청 시 프로세스 킬 없이 상주 2B로 투명 라우팅, SM 6.1 FlashAttn 생략 + Q8 KV 적용
------------------------------------------------------------------------------------------------------------------------
[Tier 2: 11~12GB 확장]       GTX 1080Ti / RTX 3060  Qwen 3.5 4B (Q4_K_M)   16K (16,384)      GPU VRAM 100%       8.5 GB (여유 2.5~3.5GB)
                             * 4B 100% 네이티브 상주 가동, RTX 3060(SM 8.6) 이상 시 FlashAttention-3 자동 활성화
------------------------------------------------------------------------------------------------------------------------
[Tier 3: 16~24GB+ 엔터프라이즈] RTX 4080 / 4090 / A100 Qwen 3.5 9B 또는 4B(64K) 16K ~ 64K        GPU VRAM 100%       11.0 ~ 16.0 GB (초대형)
========================================================================================================================
```

---

## 3. User Scenarios & Testing *(mandatory)*

### User Story 1 - 8GB 환경 2B 32K 상주 & 11/12GB 4B 듀얼 아키텍처 구축 (Priority: P1) 🎯 MVP

운영자가 시스템을 기동할 때, 8GB GPU(GTX 1070)에서는 `qwen3.5-2b`와 BGE 모델 2종이 GPU VRAM 3.7GB 이내로 안전 상주하며, 11GB(GTX 1080Ti)/12GB(RTX 3060) 환경으로 이전하거나 설정을 변경하면 코드 수정 없이 즉시 `qwen3.5-4b (16K)` 네이티브 상주 모드로 활성화된다.

**Why this priority**: 현재 하드웨어(8GB)의 OOM 위험을 0건으로 통제함과 동시에, 향후 하드웨어 업그레이드 시 즉시 스위칭 가능한 무손실 아키텍처를 완성합니다.

**Independent Test**: 8GB 모드(`SINGLE_MODEL_MODE=true`)에서 4B 호출 시 2B로 투명 라우팅됨을 검증하고, 모의 12GB 모드(`SINGLE_MODEL_MODE=false`)에서 4B가 정상 로드되는지 단위 테스트로 검증.

**Acceptance Scenarios**:
1. **Given** 8GB GPU 환경일 때, **When** 시스템이 기동되면, **Then** `qwen3.5-2b` (16K~32K) + `bge-m3` + `bge-reranker`가 모두 GPU에 상주하여 총 VRAM 점유량은 3.7GB 이하를 유지한다.
2. **Given** 11GB/12GB GPU 환경(또는 `SINGLE_MODEL_MODE=false`)일 때, **When** `qwen3.5-4b` 로드를 요청하면, **Then** 4B 모델과 BGE 2종이 모두 GPU에 상주하여 고품질 4B 추론을 직접 수행한다.

---

### User Story 2 - 전사 레거시 하드코딩 전수 점검 및 단일 진실 소스화 (Priority: P2)

`model_gateway`, `bteam/oliview_core`, `ateam/pilos`, 전사 테스트 스위트 곳곳에 남아있는 구버전 하드코딩 문자열(예: `qwen3.5-4b` fallback, 포트 번호, VRAM 매직 넘버)을 전수 교체하고 `ConfigManager` 단일 진실 소스로 일원화한다.

**Why this priority**: 코드 내부의 하드코딩 잔재로 인한 런타임 불일치 및 예기치 않은 오작동을 원천 차단합니다.

**Independent Test**: 전사 정적 분석 스크립트로 하드코딩된 레거시 fallback 문자열이 0건임을 확인하고, 전사 회귀 테스트가 100% 통과하는지 검증.

**Acceptance Scenarios**:
1. **Given** `inference_api.py`, `llama_manager.py`, `pilos/`의 모든 모델/포트 처리부에서, **When** 설정을 조회하면, **Then** 코드 내 하드코딩 대신 `ConfigManager` 및 중앙 설정 파일에서 동적으로 값을 읽어온다.
2. **Given** `ateam/` 및 전사 통합/계약 테스트 파일에서, **When** 테스트를 실행하면, **Then** 구버전 정적 어설션 오류 없이 동적 설정값을 기반으로 100% 통과한다.

---

### User Story 3 - 하드웨어 인식 FlashAttention 조건부 활성화 및 Pascal Q8 KV 최적화 (Priority: P3)

시스템은 기동 시 GPU Compute Capability를 감지하여, GTX 1070(Pascal SM 6.1)에서는 FlashAttention 옵션을 안전하게 생략하고 **Q8_0 KV Cache 양자화**를 활성화하며, 향후 SM >= 8.0(RTX 3060 등) GPU 교체 시 자동으로 FlashAttention-3을 동적 활성화한다.

**Why this priority**: GTX 1070 환경에서 FlashAttention 명령어 결함으로 인한 비정상 지연/경고를 방지하고 메모리를 50% 절감합니다.

**Independent Test**: GTX 1070 환경에서 기동 로그를 확인하여 FlashAttention 경고 없이 Q8_0 KV Cache가 적용되는지 검증.

**Acceptance Scenarios**:
1. **Given** GPU Compute Capability < 8.0 (GTX 1070) 환경일 때, **When** llama-server가 기동되면, **Then** `--flash_attn` 옵션은 생략되고 `--cache-type-k q8_0 --cache-type-v q8_0`가 적용된다.
2. **Given** GPU Compute Capability >= 8.0 (RTX 3060 등) 환경일 때, **When** llama-server가 기동되면, **Then** `--flash_attn True`가 자동으로 추가 인입된다.

---

### User Story 4 - 설정 덮어쓰기(Anti-Shadowing) 방어 및 OOM 리소스 누수 격리 (Priority: P4)

함수 기본 인자(예: `n_ctx=4096`)나 하위 모듈이 상위의 16K/32K 설정을 덮어쓰지 못하도록 엄격히 가드하고, 좀비 프로세스 VRAM 누수 및 동시 추론 폭주를 원천 격리한다.

**Why this priority**: 16K/32K 대용량 컨텍스트의 안정성을 보장하고 극한 상황에서도 OOM 크래시를 0건으로 유지합니다.

**Independent Test**: 다중 동시 추론 및 프로세스 재기동 시 VRAM 누수와 설정 변조가 0건인지 카오스 테스트로 검증.

**Acceptance Scenarios**:
1. **Given** 클라이언트 요청에 `n_ctx`가 생략되었을 때, **When** 추론 파이프라인이 실행되면, **Then** 코드 기본값으로 덮어쓰지 않고 현재 상주 모델의 컨텍스트(16K/32K)를 그대로 보존한다.
2. **Given** 프로세스 종료 요청 시, **When** 프로세스가 중단되면, **Then** 소켓 바인딩 및 PID 종료를 검증하여 좀비 프로세스에 의한 VRAM 중복 점유를 원천 차단한다.

---

## 4. 요구사항 (Requirements) *(mandatory)*

### Functional Requirements

- **FR-001 (하드웨어 티어 기반 서빙 전략 구축)**: 8GB GPU에서는 `qwen3.5-2b` + BGE 2종의 GPU 상주를 기본 채택하고 4B 요청을 2B로 투명 라우팅하며, 11GB(GTX 1080Ti)/12GB(RTX 3060) 환경을 위한 `qwen3.5-4b` 16K 상주 코드를 완전 구축·보존해야 한다.
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

1. **8GB 환경 무중단 안정성**: 2B (16K~32K) + BGE 2종 GPU 상주 체제에서 VRAM 피크 3.7GB 이하 유지 및 OOM 크래시 **0건**.
2. **11GB/12GB 4B 전환 준비 완결**: 11GB/12GB 설정 활성화 시 4B (16K) 네이티브 서빙 정상 동작 확인.
3. **하드코딩 잔재 0건**: 정적 코드 분석 및 전수 검색 결과 레거시 모델명/포트 하드코딩 발생 건수 **0건**.
4. **GTX 1070 최적화**: FlashAttention 경고 0건 및 Q8_0 KV Cache 적용을 통한 50% KV VRAM 절감 실측 확인.
5. **설정값 보존율 100%**: 상위 설정(16K/32K 컨텍스트)이 내부 함수 매개변수에 의해 변조되거나 덮어씌워지는 현상 **0건**.
6. **회귀 테스트 무결점**: 전사 5대 종합 회귀 테스트 스위트 100% 통과 유지.
