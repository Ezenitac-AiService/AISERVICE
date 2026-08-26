# Feature Specification: Audit, Zero-Hardcoding, and 5-Tier GPU Architecture OOM Hardening

**Feature Branch**: `034-audit-config-oom-guards`  
**Created**: 2026-08-26  
**Status**: Ready for Planning  
**Input**: User description: "방금 케이스 같은 부분이 분명히 또 있을거야 이번 리펙토링 주제는 방금의 이슈를 중점으로 검토해서 스펙을 작성하자, 1. 하드코딩 되어있는 부분은 없는가? 2. 환경변수나, 벤치마킹등으로 설정된 설정값이 로직중에 덮어씌워지거나 무시되는 부분이 있는가? 3. 기타 oom을 유발할만한 요인이 있는가? 우리 대상 플렛폼 gpu는 gtx 1070 노말, gtx 1080ti, rtx 2080 노말, rtx 3060 12gb, rtx 4080 노말이야. 현재 플렛폼은 i7 930이라 cpu를 전혀 사용하지 않는 llama.cpp를 빌드했지만, 시스템은 하드웨어를 인식해서 알맞는 옵션으로 빌드/구동하는데, gpu 세대간 지원되는 기술과 데이터 타입이 다르니 '세대별 스펙'을 리서치해서 체크리스트를 만들고 이걸 기준으로 구축 운영하도록 고도화 반영해줘"

---

## 1. 개요 및 배경 (Context & Problem Statement)

### 1.1 현상 및 배경 (Background)
* **호스트 CPU 제약 (Intel Core i7 930, 1세대 Nehalem)**: AVX/AVX2/AVX-512 미지원 CPU이므로, 트랜스포머 신경망(LLM, BGE 임베딩, BGE 리랭커)을 CPU로 연산 시 극심한 지연이 발생합니다. 따라서 모든 신경망 연산은 **100% GPU VRAM 상주 (`-ngl 999`)**로 실행해야 합니다.
* **5대 타겟 GPU 세대별 아키텍처 특성**:
  - **GTX 1070 (Pascal SM 6.1, 8GB)** / **GTX 1080 Ti (Pascal SM 6.1, 11GB)**: Tensor Cores 없음, FlashAttention 미지원, Q8_0 KV Cache 필수.
  - **RTX 2080 (Turing SM 7.5, 8GB)**: 1세대 Tensor Cores, FP16 네이티브, FlashAttention 제한적, Q8_0 KV Cache 적용.
  - **RTX 3060 12GB (Ampere SM 8.6, 12GB)**: 2세대 Tensor Cores, BF16/TF32 지원, FlashAttention-2/3 완전 지원.
  - **RTX 4080 (Ada Lovelace SM 8.9, 16GB)**: 3세대 Tensor Cores, FP8 (Transformer Engine) / FlashAttention-3 완전 지원.
* 시스템은 기동 시 GPU Compute Capability와 VRAM을 실측하여, **새로운 GPU 세대가 출시되지 않는 한 영구 불변의 '세대별 스펙 체크리스트'**를 기반으로 최적 플래그(FlashAttn, Q8 KV, FP8)와 동적 컨텍스트 윈도우($n_{\text{ctx}}$: 16K~128K)를 자율 결정합니다.

---

## 2. 5대 GPU 세대별 불변 하드웨어 스펙 체크리스트 (Immutable Hardware Matrix)

```text
==========================================================================================================================================
GPU 모델명            아키텍처      CUDA SM   VRAM 용량   Tensor Cores   FP16/BF16/FP8   FlashAttn-3   KV 양자화 권장   권장 모델 & 동적 컨텍스트
==========================================================================================================================================
1. GTX 1070 (노말)    Pascal       SM 6.1    8 GB        없음 (None)    FP32 표준       ❌ 미지원      Q8_0 KV Cache   Qwen 3.5 2B @ 16K ~ 32K
2. GTX 1080 Ti       Pascal       SM 6.1    11 GB       없음 (None)    FP32 표준       ❌ 미지원      Q8_0 KV Cache   Qwen 3.5 4B @ 32K ~ 48K
3. RTX 2080 (노말)    Turing       SM 7.5    8 GB        1세대 텐서     FP16 네이티브   ⚠️ 생략권장    Q8_0 KV Cache   Qwen 3.5 2B @ 32K
4. RTX 3060 (12GB)   Ampere       SM 8.6    12 GB       2세대 텐서     FP16/BF16/TF32  ✅ 완전지원    Q8_0 or FP16    Qwen 3.5 4B @ 64K (초장문)
5. RTX 4080 (노말)    Ada Lovelace SM 8.9    16 GB       3세대 텐서     FP16/BF16/FP8   ✅ 완전지원    FP8 / Q8_0      Qwen 3.5 4B @ 128K / 9B @ 32K
==========================================================================================================================================
* 공통: BGE 임베딩(706MB) + BGE 리랭커(706MB) = 1.4GB는 5대 플랫폼 전역에서 100% GPU VRAM 상주 고정.
```

---

## 3. User Scenarios & Testing *(mandatory)*

### User Story 1 - 5대 GPU 세대별 자율 하드웨어 감지 & 최적 서빙 (Priority: P1) 🎯 MVP

운영자가 임의의 타겟 GPU(GTX 1070, GTX 1080Ti, RTX 2080, RTX 3060, RTX 4080)에서 시스템을 기동하면, 게이트웨이는 Compute Capability와 VRAM을 실측하여 세대별 불변 체크리스트에 따라 FlashAttention 플래그, KV 양자화 타입, 최적 모델 및 컨텍스트 윈도우 크기를 100% 자동으로 구성하여 서빙한다.

**Why this priority**: 하드웨어가 바뀌더라도 코드 수정이나 재빌드 없이 단일 바이너리로 각 GPU 세대에 최적화된 최대 성능을 무결점으로 발휘합니다.

**Independent Test**: 모의 GPU 스펙(SM 6.1 8GB, SM 6.1 11GB, SM 7.5 8GB, SM 8.6 12GB, SM 8.9 16GB)을 주입하여 `detect_gpu_capabilities()`가 반환하는 플래그와 모델이 5대 매트릭스와 정확히 일치하는지 검증.

**Acceptance Scenarios**:
1. **Given** GTX 1070 (SM 6.1, 8GB)일 때, **When** 시스템이 기동되면, **Then** `--flash_attn`은 생략되고 `--cache-type-k q8_0 --cache-type-v q8_0`가 적용되어 2B 모델이 16K~32K로 안전 상주한다.
2. **Given** RTX 3060 (SM 8.6, 12GB)일 때, **When** 시스템이 기동되면, **Then** `--flash_attn True`와 `--cache-type-k q8_0`가 적용되어 4B 모델이 64K 컨텍스트로 상주한다.
3. **Given** RTX 4080 (SM 8.9, 16GB)일 때, **When** 시스템이 기동되면, **Then** `--flash_attn True`와 FP8 양자화가 적용되어 4B @ 128K 또는 9B @ 32K가 상주한다.

---

### User Story 2 - 전사 레거시 하드코딩 전수 점검 및 단일 진실 소스화 (Priority: P2)

`model_gateway`, `bteam/oliview_core`, `ateam/pilos`, 전사 테스트 스위트 곳곳에 남아있는 구버전 하드코딩 문자열(예: `qwen3.5-4b` fallback, 포트 번호, VRAM 매직 넘버)을 전수 교체하고 `ConfigManager` 단일 진실 소스로 일원화한다.

**Why this priority**: 코드 내부의 하드코딩 잔재로 인한 런타임 불일치 및 예기치 않은 오작동을 원천 차단합니다.

**Independent Test**: 전사 정적 분석 스크립트로 하드코딩된 레거시 fallback 문자열이 0건임을 확인하고, 전사 회귀 테스트가 100% 통과하는지 검증.

**Acceptance Scenarios**:
1. **Given** `inference_api.py`, `llama_manager.py`, `pilos/`의 모든 모델/포트 처리부에서, **When** 설정을 조회하면, **Then** 코드 내 하드코딩 대신 `ConfigManager` 및 중앙 설정 파일에서 동적으로 값을 읽어온다.
2. **Given** `ateam/` 및 전사 통합/계약 테스트 파일에서, **When** 테스트를 실행하면, **Then** 구버전 정적 어설션 오류 없이 동적 설정값을 기반으로 100% 통과한다.

---

### User Story 3 - 설정 덮어쓰기(Anti-Shadowing) 방어 및 OOM 리소스 누수 격리 (Priority: P3)

함수 기본 인자(예: `n_ctx=4096`)나 하위 모듈이 상위의 동적 컨텍스트 설정을 덮어쓰지 못하도록 엄격히 가드하고, 좀비 프로세스 VRAM 누수 및 동시 추론 폭주를 원천 격리한다.

**Why this priority**: 동적으로 산출된 대용량 컨텍스트의 안정성을 보장하고 극한 상황에서도 OOM 크래시를 0건으로 유지합니다.

**Independent Test**: 다중 동시 추론 및 프로세스 재기동 시 VRAM 누수와 설정 변조가 0건인지 카오스 테스트로 검증.

**Acceptance Scenarios**:
1. **Given** 클라이언트 요청에 `n_ctx`가 생략되었을 때, **When** 추론 파이프라인이 실행되면, **Then** 코드 기본값으로 덮어쓰지 않고 현재 동적 산출된 컨텍스트 크기를 그대로 보존한다.
2. **Given** 프로세스 종료 요청 시, **When** 프로세스가 중단되면, **Then** 소켓 바인딩 및 PID 종료를 검증하여 좀비 프로세스에 의한 VRAM 중복 점유를 원천 차단한다.

---

## 4. 요구사항 (Requirements) *(mandatory)*

### Functional Requirements

- **FR-001 (5대 GPU 세대별 불변 스펙 체크리스트 구축)**: `gpu_detector.py`에 Pascal(SM 6.1), Turing(SM 7.5), Ampere(SM 8.6), Ada Lovelace(SM 8.9) 아키텍처별 불변 룩업 테이블(`GPU_ARCHITECTURE_SPEC_TABLE`)을 구축하고 실시간 자동 매칭해야 한다.
- **FR-002 (동적 VRAM 벤치마킹 & 컨텍스트 사이징 엔진)**: 물리 VRAM 실측값 및 가용 메모리 예산 수식에 따라 최적 모델(2B/4B/9B)과 최대 안전 컨텍스트 윈도우($n_{\text{ctx}}$: 16K~128K)를 동적으로 산출해야 한다.
- **FR-003 (8GB 플랫폼 상주 가드 및 4B 투명 라우팅)**: 8GB GPU에서는 `qwen3.5-2b` + BGE 2종의 GPU 상주를 기본 채택하고 4B 요청을 2B로 투명 라우팅하며, 11GB+ 환경에서는 4B/9B 네이티브 서빙을 활성화해야 한다.
- **FR-004 (하드웨어 인식 FlashAttention & Q8/FP8 KV)**: GPU Compute Capability에 따라 SM < 8.0에서는 FlashAttention을 생략하고 Q8_0 KV Cache를 적용하며, SM >= 8.0에서는 FlashAttention-3을, SM 8.9에서는 FP8 KV 캐시를 자동 활성화해야 한다.
- **FR-005 (하드코딩 전수 점검 및 제거)**: `model_gateway`, `bteam/oliview_core`, `ateam/pilos`, `tests/` 전역에서 하드코딩된 레거시 모델명(`qwen3.5-4b` fallback), 포트 번호, VRAM 매직 넘버를 `ConfigManager`로 교체해야 한다.
- **FR-006 (엄격한 설정 계층화 및 Anti-Shadowing)**: 설정 우선순위를 `[1] 요청 페이로드 > [2] 환경변수 > [3] 동적 VRAM 사이징 프로파일 > [4] server_config.json > [5] model_config.json > [6] 안전 기본값`으로 명문화하고 하위 계층에 의한 덮어쓰기를 엄격히 금지해야 한다.
- **FR-007 (컨텍스트 윈도우 무변조 보장)**: 모든 `n_ctx` 처리 로직에서 요청에 명시되지 않은 경우 임의의 축소값(4096)이 아닌 동적으로 산출된 컨텍스트 크기를 일관되게 주입해야 한다.
- **FR-008 (로딩 프로세스 Cascade Kill 방지)**: `llama_manager.py`는 `LOADING` 상태의 프로세스가 있을 때 중복 요청 유입 시 프로세스를 강제 종료하지 않고 완료 대기(`_wait_for_ready`)해야 한다.
- **FR-009 (VRAM 안전 상한선 및 프리플라이트 수식 교정)**: `calculate_base_vram_mb`는 GQA 및 Q8 KV 캐시 수식을 정확히 반영하여 허위 OOM 거절을 방지해야 한다.
- **FR-010 (동시성 세마포어 및 공정 큐 제어)**: `AsyncFairQueue`와 클라이언트 레벨의 `_gpu_semaphore(max=3)`가 연동되어 동시 추론 폭주를 방어해야 한다.
- **FR-011 (좀비 프로세스 소켓 점유 방어)**: 서빙 프로세스 시작 전 이전 프로세스의 소켓 바인딩 해제 및 VRAM 해제를 검증하고, 미종료 프로세스는 `kill -9`로 강제 회수해야 한다.
- **FR-012 (Redis & L5 캐시 메모리 상한 관리)**: Redis 설정에 `maxmemory 512mb` 및 `maxmemory-policy allkeys-lru`를 적용하여 무제한 메모리 팽창을 방어해야 한다.

---

## 5. Success Criteria *(mandatory)*

1. **5대 GPU 아키텍처 자동 감지 100%**: GTX 1070(6.1), GTX 1080Ti(6.1), RTX 2080(7.5), RTX 3060(8.6), RTX 4080(8.9) 모의 주입 시 100% 정확한 아키텍처 및 플래그 매칭 확인.
2. **동적 컨텍스트 사이징 검증**: 8GB(16K~32K), 11GB(32K~48K), 12GB(64K), 16GB(128K) 가상 VRAM 주입 시 100% 정확한 동적 산출 확인.
3. **8GB 환경 무중단 안정성**: 2B (16K~32K) + BGE 2종 GPU 상주 체제에서 VRAM 피크 3.7GB 이하 유지 및 OOM 크래시 **0건**.
4. **하드코딩 잔재 0건**: 정적 코드 분석 및 전수 검색 결과 레거시 모델명/포트 하드코딩 발생 건수 **0건**.
5. **설정값 보존율 100%**: 상위 동적 설정 컨텍스트가 내부 함수 매개변수에 의해 변조되거나 덮어씌워지는 현상 **0건**.
6. **회귀 테스트 무결점**: 전사 5대 종합 회귀 테스트 스위트 100% 통과 유지.
