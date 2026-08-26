# Feature Specification: Audit, Zero-Hardcoding, and 6-Tier CPU-GPU Paired Architecture OOM Hardening

**Feature Branch**: `034-audit-config-oom-guards`  
**Created**: 2026-08-26  
**Status**: Ready for Planning  
**Input**: User description: "방금 케이스 같은 부분이 분명히 또 있을거야 이번 리펙토링 주제는 방금의 이슈를 중점으로 검토해서 스펙을 작성하자, 1. 하드코딩 되어있는 부분은 없는가? 2. 환경변수나, 벤치마킹등으로 설정된 설정값이 로직중에 덮어씌워지거나 무시되는 부분이 있는가? 3. 기타 oom을 유발할만한 요인이 있는가? 우리 대상 플렛폼 gpu는 gtx 1070 노말, gtx 1080ti, rtx 2080 노말, rtx 3060 12gb, rtx 4080 노말, 5천번대(5060ti 16gb, 5080)야. i7 930은 gtx 1070에만 사용될거고, 다른 gpu들은 그에 맞는 gpu 병목이 발생하지 않을 세대의 인텔 cpu를 사용해. gpu 세대간 지원되는 기술과 데이터 타입을 체크리스트로 만들고 구축 운영하도록 고도화 반영해줘"

---

## 1. 개요 및 배경 (Context & Problem Statement)

### 1.1 현상 및 배경 (Background)
* **CPU-GPU 하드웨어 페어링 토폴로지**:
  - **Tier 1 (GTX 1070 8GB 전용)**: Intel Core i7 930 (1세대 Nehalem, AVX/AVX2 미지원). 신경망 CPU 연산 시 극심한 지연이 발생하므로 모든 모델(LLM, BGE 2종)을 **100% GPU VRAM 상주 (`-ngl 999`)**로 실행해야 합니다.
  - **Tier 2 ~ Tier 6 (GTX 1080Ti ~ RTX 5000번대)**: GPU 병목이 없는 **현대적 Intel CPU (AVX2 / FMA3 / PCIe 4.0/5.0 지원)**와 페어링되어, 고속 토큰 전처리 및 호스트-디바이스 DMA 고속 전송을 온전히 활용합니다.
* 시스템은 기동 시 CPU 명령어 세트(AVX/AVX2)와 GPU Compute Capability(SM 6.1~12.0) 및 물리 VRAM을 실측하여, **불변의 6대 CPU-GPU 하드웨어 스펙 체크리스트**에 따라 최적 컴파일/런타임 플래그(FlashAttn, Q8/FP8/FP4 KV, `-ngl 999`)와 동적 컨텍스트 윈도우($n_{\text{ctx}}$: 16K~128K)를 자율 결정합니다.

---

## 2. 6대 CPU-GPU 페어링 불변 하드웨어 스펙 체크리스트 (Hardware Pairing Matrix)

```text
======================================================================================================================================================
플랫폼 티어        GPU 모델 (아키텍처/VRAM)     페어링 Intel CPU (세대/특성)           CPU 명령어 지원      FlashAttn-3/4   KV 양자화 권장   권장 모델 & 동적 컨텍스트
======================================================================================================================================================
1. Tier 1 (기본)  GTX 1070 (Pascal SM 6.1, 8G) Intel Core i7 930 (1세대 Nehalem)   SSE4.2 (AVX 없음)   ❌ 미지원        Q8_0 KV Cache   Qwen 3.5 2B @ 16K ~ 32K
                  * i7 930 전용: AVX 미지원으로 100% GPU VRAM 상주 (-ngl 999) 필수, CPU 연산 배제
------------------------------------------------------------------------------------------------------------------------------------------------------
2. Tier 2 (확장)  GTX 1080 Ti (Pascal, 11G)    Intel Core i7 7th/8th Gen           AVX2 / FMA3         ❌ 미지원        Q8_0 KV Cache   Qwen 3.5 4B @ 32K ~ 48K
3. Tier 3 (확장)  RTX 2080 (Turing, 8G)        Intel Core i7 9th/10th Gen          AVX2 / FMA3         ⚠️ 생략권장      Q8_0 KV Cache   Qwen 3.5 2B @ 32K
4. Tier 4 (확장)  RTX 3060 12GB (Ampere, 12G)  Intel Core i5/i7 12th/13th Gen      AVX2 / PCIe 4.0     ✅ 완전지원      Q8_0 or FP16    Qwen 3.5 4B @ 64K (초장문)
5. Tier 5 (엔터)  RTX 4080 (Ada, 16G)          Intel Core i7 13th/14th Gen         AVX2 / PCIe 4.0/5.0 ✅ 완전지원      FP8 / Q8_0      Qwen 3.5 4B @ 128K / 9B @ 32K
6. Tier 6 (하이)  RTX 5060Ti/5080 (Blackwell)  Intel Core Ultra / 14th Gen         AVX2 / AVX-VNNI     ✅ FA-3/4 (TMA)  FP4 / FP8 / Q8  Qwen 3.5 9B @ 64K ~ 128K
======================================================================================================================================================
* 공통 고정: BGE 임베딩(706MB) + BGE 리랭커(706MB) = 1.4GB는 6대 플랫폼 전역에서 100% GPU VRAM 상주 고정.
```

---

## 3. User Scenarios & Testing *(mandatory)*

### User Story 1 - 6대 CPU-GPU 페어링 자율 하드웨어 감지 & 최적 서빙 (Priority: P1) 🎯 MVP

운영자가 임의의 타겟 플랫폼(Tier 1의 i7 930 + GTX 1070부터 Tier 6의 최신 Intel + RTX 5000번대까지)에서 시스템을 기동하면, 게이트웨이는 CPU 명령어 세트(AVX 유무)와 GPU Compute Capability 및 VRAM을 실측하여 세대별 불변 체크리스트에 따라 플래그, 모델, 컨텍스트 크기를 100% 자동으로 구성하여 서빙한다.

**Why this priority**: 플랫폼별 CPU-GPU 하드웨어 조합에 따라 병목을 원천 방지하고 단일 바이너리/컨테이너로 각 환경에 최적화된 최대 성능을 무결점으로 발휘합니다.

**Independent Test**: 모의 하드웨어 스펙(i7 930+GTX 1070, i7+GTX 1080Ti, i7+RTX 3060, Ultra+RTX 5080)을 주입하여 `detect_hardware_capabilities()`가 반환하는 플래그와 모델이 6대 매트릭스와 정확히 일치하는지 검증.

**Acceptance Scenarios**:
1. **Given** Tier 1 (i7 930 + GTX 1070)일 때, **When** 시스템이 기동되면, **Then** AVX 부재를 감지하여 `-ngl 999`로 100% GPU VRAM 상주를 강제하고 FlashAttention은 생략되며 Q8_0 KV Cache가 적용된다.
2. **Given** Tier 4 (현대적 Intel CPU + RTX 3060 12GB)일 때, **When** 시스템이 기동되면, **Then** AVX2 및 FlashAttention-2/3이 자동 켜지고 4B 모델이 64K 컨텍스트로 상주한다.
3. **Given** Tier 6 (최신 Intel + RTX 5060Ti/5080)일 때, **When** 시스템이 기동되면, **Then** FlashAttention-4(TMA)와 FP8/FP4 KV 캐시가 적용되어 9B @ 128K가 상주한다.

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

- **FR-001 (6대 CPU-GPU 하드웨어 페어링 체크리스트 구축)**: `gpu_detector.py`에 CPU(AVX 지원 여부) 및 GPU(Pascal~Blackwell SM 6.1~12.0) 불변 룩업 테이블을 구축하고 실시간 자동 매칭해야 한다.
- **FR-002 (Tier 1 i7 930 특화 100% GPU VRAM Offload 가드)**: AVX 미지원 CPU(i7 930) 감지 시 모든 신경망 연산에 `-ngl 999`를 강제 적용하여 CPU 연산 병목을 원천 방어해야 한다.
- **FR-003 (동적 VRAM 벤치마킹 & 컨텍스트 사이징 엔진)**: 물리 VRAM 실측값 및 가용 메모리 예산 수식에 따라 최적 모델(2B/4B/9B)과 최대 안전 컨텍스트 윈도우($n_{\text{ctx}}$: 16K~128K)를 동적으로 산출해야 한다.
- **FR-004 (8GB 플랫폼 상주 가드 및 4B 투명 라우팅)**: 8GB GPU에서는 `qwen3.5-2b` + BGE 2종의 GPU 상주를 기본 채택하고 4B 요청을 2B로 투명 라우팅하며, 11GB+ 환경에서는 4B/9B 네이티브 서빙을 활성화해야 한다.
- **FR-005 (하드웨어 인식 FlashAttention & Q8/FP8/FP4 KV)**: GPU Compute Capability에 따라 SM < 8.0에서는 FlashAttention을 생략하고 Q8_0 KV Cache를 적용하며, SM >= 8.0에서는 FlashAttention-3을, SM 8.9/12.0에서는 FP8/FP4 KV 캐시를 자동 활성화해야 한다.
- **FR-006 (하드코딩 전수 점검 및 제거)**: `model_gateway`, `bteam/oliview_core`, `ateam/pilos`, `tests/` 전역에서 하드코딩된 레거시 모델명(`qwen3.5-4b` fallback), 포트 번호, VRAM 매직 넘버를 `ConfigManager`로 교체해야 한다.
- **FR-007 (엄격한 설정 계층화 및 Anti-Shadowing)**: 설정 우선순위를 `[1] 요청 페이로드 > [2] 환경변수 > [3] 동적 VRAM 사이징 프로파일 > [4] server_config.json > [5] model_config.json > [6] 안전 기본값`으로 명문화하고 하위 계층에 의한 덮어쓰기를 엄격히 금지해야 한다.
- **FR-008 (컨텍스트 윈도우 무변조 보장)**: 모든 `n_ctx` 처리 로직에서 요청에 명시되지 않은 경우 임의의 축소값(4096)이 아닌 동적으로 산출된 컨텍스트 크기를 일관되게 주입해야 한다.
- **FR-009 (로딩 프로세스 Cascade Kill 방지)**: `llama_manager.py`는 `LOADING` 상태의 프로세스가 있을 때 중복 요청 유입 시 프로세스를 강제 종료하지 않고 완료 대기(`_wait_for_ready`)해야 한다.
- **FR-010 (VRAM 안전 상한선 및 프리플라이트 수식 교정)**: `calculate_base_vram_mb`는 GQA 및 Q8 KV 캐시 수식을 정확히 반영하여 허위 OOM 거절을 방지해야 한다.
- **FR-011 (동시성 세마포어 및 공정 큐 제어)**: `AsyncFairQueue`와 클라이언트 레벨의 `_gpu_semaphore(max=3)`가 연동되어 동시 추론 폭주를 방어해야 한다.
- **FR-012 (좀비 프로세스 소켓 점유 방어)**: 서빙 프로세스 시작 전 이전 프로세스의 소켓 바인딩 해제 및 VRAM 해제를 검증하고, 미종료 프로세스는 `kill -9`로 강제 회수해야 한다.
- **FR-013 (Redis & L5 캐시 메모리 상한 관리)**: Redis 설정에 `maxmemory 512mb` 및 `maxmemory-policy allkeys-lru`를 적용하여 무제한 메모리 팽창을 방어해야 한다.

---

## 5. Success Criteria *(mandatory)*

1. **6대 CPU-GPU 하드웨어 자동 감지 100%**: i7 930+GTX 1070부터 최신 Intel+RTX 5080까지 모의 주입 시 100% 정확한 아키텍처 및 플래그 매칭 확인.
2. **동적 컨텍스트 사이징 검증**: 8GB(16K~32K), 11GB(32K~48K), 12GB(64K), 16GB(128K) 가상 VRAM 주입 시 100% 정확한 동적 산출 확인.
3. **8GB i7 930 환경 무중단 안정성**: 2B (16K~32K) + BGE 2종 GPU 상주 체제에서 VRAM 피크 3.7GB 이하 유지 및 OOM 크래시 **0건**.
4. **하드코딩 잔재 0건**: 정적 코드 분석 및 전수 검색 결과 레거시 모델명/포트 하드코딩 발생 건수 **0건**.
5. **설정값 보존율 100%**: 상위 동적 설정 컨텍스트가 내부 함수 매개변수에 의해 변조되거나 덮어씌워지는 현상 **0건**.
6. **회귀 테스트 무결점**: 전사 5대 종합 회귀 테스트 스위트 100% 통과 유지.
