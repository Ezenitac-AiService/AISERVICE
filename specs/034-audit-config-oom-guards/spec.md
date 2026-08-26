# Feature Specification: Audit, Zero-Hardcoding, and Hardware-Tiered Dynamic Context OOM Hardening

**Feature Branch**: `034-audit-config-oom-guards`  
**Created**: 2026-08-26  
**Status**: Ready for Planning  
**Input**: User description: "방금 케이스 같은 부분이 분명히 또 있을거야 이번 리펙토링 주제는 방금의 이슈를 중점으로 검토해서 스펙을 작성하자, 1. 하드코딩 되어있는 부분은 없는가? 2. 환경변수나, 벤치마킹등으로 설정된 설정값이 로직중에 덮어씌워지거나 무시되는 부분이 있는가? 3. 기타 oom을 유발할만한 요인이 있는가? 4b 모델을 사용하는 전략은 11gb vram 플렛폼(gtx 1080ti), 12gb vram 플렛폼(rtx 3060)들을 위해서 구축하고 지금 이 gtx 1070 플렛폼에서는 비활성화 하는 방향으로. 더 많은 vram 플렛폼에서는 컨텍스트 윈도우 크기도 거기에 맞춰서 동적으로 벤치마킹하고 셋팅해야지 16k로 지정하지 말고"

---

## 1. 개요 및 배경 (Context & Problem Statement)

### 1.1 현상 및 배경 (Background)
* **8GB GPU (NVIDIA GTX 1070, Windows OS 점유 ~3.7GB)** 환경에서 시스템 총 VRAM(8.19GB) 한계를 절대 초과하지 않으면서 50ms급 고속 RAG를 제공하기 위해, **BGE 임베딩(0.7GB)과 BGE 리랭커(0.7GB)는 반드시 GPU VRAM에 상주**해야 합니다 (CPU 실행 시 6~10초 지연으로 챗봇 타임아웃 발생).
* 이에 따라 8GB GPU 환경에서는 **2B 모델(16K~32K 컨텍스트) + BGE 2종의 GPU 동시 상주(총 3.3~3.7GB)**를 기본 활성화하고, 다단계 에이전틱 리플렉션 루프(TTC)를 통해 추론 품질을 보완합니다.
* **4B/9B 모델 및 고용량 VRAM 플랫폼**: 16K로 고정하지 않고, **VRAM 용량(11GB, 12GB, 16GB, 24GB+)에 따라 사용 가능한 잔여 VRAM을 실시간 벤치마킹하여 컨텍스트 윈도우 크기($n_{\text{ctx}}$: 16K $\rightarrow$ 32K $\rightarrow$ 64K $\rightarrow$ 128K)를 동적으로 자동 산출·할당**합니다.
* **현재 8GB GTX 1070 플랫폼**: 하드웨어 감지 가드를 통해 4B 요청을 상주 2B로 투명 라우팅하며, Pascal SM 6.1 특성에 맞춰 FlashAttention을 안전 생략하고 **Q8_0 KV Cache 양자화**를 적용합니다.

---

## 2. VRAM 기반 동적 컨텍스트 윈도우 벤치마킹 & 사이징 수식 (Dynamic Context Sizing Formula)

게이트웨이 기동 시 `ConfigManager` 및 `gpu_detector.py`가 물리 VRAM을 측정하고 다음 수식에 따라 **최적 모델 및 최대 안전 컨텍스트 윈도우($n_{\text{ctx}}$)**를 동적으로 결정합니다:

$$\begin{aligned}
V_{\text{LLM\_Budget}} &= V_{\text{Total\_VRAM}} - V_{\text{OS\_Reserved}}(3,700\text{MB}) - V_{\text{BGE\_Aux}}(1,412\text{MB}) - V_{\text{Safety\_Margin}}(600\sim1,500\text{MB}) \\
V_{\text{KV\_Budget}} &= V_{\text{LLM\_Budget}} - W_{\text{Model\_Weight}} \\
n_{\text{ctx\_dynamic}} &= \min\left(n_{\text{Model\_Native\_Max}}, \left\lfloor \frac{V_{\text{KV\_Budget}}}{\text{Bytes\_per\_token\_KV(Q8\_0)}} \right\rfloor \right) \quad \text{(Snap to 16K, 32K, 64K, 128K)}
\end{aligned}$$

```text
=================================================================================================================================
하드웨어 티어            물리 VRAM   선택 모델        동적 산출 컨텍스트 윈도우 (n_ctx)   FlashAttn-3   특징 및 역할
=================================================================================================================================
[Tier 1: 8GB 기본]       8 GB       Qwen 3.5 2B      16K ~ 32K (16,384 ~ 32,768)        생략 (Q8 KV)  8GB OOM 0건 완벽 상주 + 에이전틱 루프
[Tier 2: 11GB 확장]      11 GB      Qwen 3.5 4B      32K ~ 48K (32,768 ~ 49,152)        생략 (Q8 KV)  GTX 1080Ti 고용량 4B 상주
[Tier 3: 12GB 확장]      12 GB      Qwen 3.5 4B      64K (65,536 초장문)                자동 활성화   RTX 3060/4070 4B 64K 풀 상주
[Tier 4: 16GB 엔터프라이즈] 16 GB   Qwen 3.5 4B / 9B 128K (4B) / 32K (9B)               자동 활성화   RTX 4080 초대형 문서 전수 분석
[Tier 5: 24GB+ 하이엔드] 24 GB+     Qwen 3.5 9B      128K (131,072 초대형)              자동 활성화   RTX 3090/4090/A100 플래그십 서빙
=================================================================================================================================
```

---

## 3. User Scenarios & Testing *(mandatory)*

### User Story 1 - VRAM 기반 동적 모델 & 컨텍스트 자동 벤치마킹 서빙 (Priority: P1) 🎯 MVP

운영자가 시스템을 기동할 때, 게이트웨이는 물리 VRAM 용량을 실측하여 8GB에서는 `2B (16K~32K)`, 11GB에서는 `4B (32K~48K)`, 12GB에서는 `4B (64K)`, 24GB에서는 `9B (128K)`로 모델과 컨텍스트 윈도우 크기를 동적으로 자동 셋팅하여 무중단 서빙한다.

**Why this priority**: 하드웨어가 업그레이드될 때마다 코드를 수동 수정하거나 16K로 낭비하지 않고, VRAM의 가용량을 100% 최대로 활용하는 지능형 서빙 체계를 완성합니다.

**Independent Test**: 모의 VRAM 환경(8GB, 11GB, 12GB, 24GB)을 주입하여 `ConfigManager`가 산출하는 `active_model`과 `current_n_ctx`가 위 매트릭스와 100% 일치하는지 단위 테스트로 검증.

**Acceptance Scenarios**:
1. **Given** 8GB GPU 환경일 때, **When** 시스템이 기동되면, **Then** `qwen3.5-2b`와 16K~32K 컨텍스트가 자동 바인딩되어 VRAM 3.7GB 이하를 유지한다.
2. **Given** 12GB GPU 환경일 때, **When** 시스템이 기동되면, **Then** `qwen3.5-4b`와 64K(`n_ctx=65536`) 컨텍스트가 자동 바인딩되고 FlashAttention이 켜진다.

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

함수 기본 인자(예: `n_ctx=4096`)나 하위 모듈이 상위의 동적 컨텍스트 설정을 덮어쓰지 못하도록 엄격히 가드하고, 좀비 프로세스 VRAM 누수 및 동시 추론 폭주를 원천 격리한다.

**Why this priority**: 동적으로 산출된 대용량 컨텍스트의 안정성을 보장하고 극한 상황에서도 OOM 크래시를 0건으로 유지합니다.

**Independent Test**: 다중 동시 추론 및 프로세스 재기동 시 VRAM 누수와 설정 변조가 0건인지 카오스 테스트로 검증.

**Acceptance Scenarios**:
1. **Given** 클라이언트 요청에 `n_ctx`가 생략되었을 때, **When** 추론 파이프라인이 실행되면, **Then** 코드 기본값으로 덮어쓰지 않고 현재 동적 산출된 컨텍스트 크기를 그대로 보존한다.
2. **Given** 프로세스 종료 요청 시, **When** 프로세스가 중단되면, **Then** 소켓 바인딩 및 PID 종료를 검증하여 좀비 프로세스에 의한 VRAM 중복 점유를 원천 차단한다.

---

## 4. 요구사항 (Requirements) *(mandatory)*

### Functional Requirements

- **FR-001 (동적 VRAM 벤치마킹 & 컨텍스트 사이징 엔진)**: 시스템은 물리 VRAM 실측값 및 가용 메모리 예산 수식에 따라 최적 모델(2B/4B/9B)과 최대 안전 컨텍스트 윈도우($n_{\text{ctx}}$: 16K~128K)를 동적으로 산출하여 설정해야 한다.
- **FR-002 (8GB 플랫폼 상주 가드 및 4B 투명 라우팅)**: 8GB GPU에서는 `qwen3.5-2b` + BGE 2종의 GPU 상주를 기본 채택하고 4B 요청을 2B로 투명 라우팅하며, 11GB+ 환경에서는 4B/9B 네이티브 서빙을 활성화해야 한다.
- **FR-003 (하드웨어 인식 FlashAttention & Q8 KV)**: `gpu_detector.py`는 GPU Compute Capability를 감지하여 SM < 8.0(GTX 1070)에서는 FlashAttention을 생략하고 Q8_0 KV Cache를 적용하며, SM >= 8.0에서는 FlashAttention을 자동 활성화해야 한다.
- **FR-004 (하드코딩 전수 점검 및 제거)**: `model_gateway`, `bteam/oliview_core`, `ateam/pilos`, `tests/` 전역에서 하드코딩된 레거시 모델명(`qwen3.5-4b` fallback), 포트 번호, VRAM 매직 넘버를 `ConfigManager`로 교체해야 한다.
- **FR-005 (엄격한 설정 계층화 및 Anti-Shadowing)**: 설정 우선순위를 `[1] 요청 페이로드 > [2] 환경변수 > [3] 동적 VRAM 사이징 프로파일 > [4] server_config.json > [5] model_config.json > [6] 안전 기본값`으로 명문화하고 하위 계층에 의한 덮어쓰기를 엄격히 금지해야 한다.
- **FR-006 (컨텍스트 윈도우 무변조 보장)**: 모든 `n_ctx` 처리 로직에서 요청에 명시되지 않은 경우 임의의 축소값(4096)이 아닌 동적으로 산출된 컨텍스트 크기를 일관되게 주입해야 한다.
- **FR-007 (로딩 프로세스 Cascade Kill 방지)**: `llama_manager.py`는 `LOADING` 상태의 프로세스가 있을 때 중복 요청 유입 시 프로세스를 강제 종료하지 않고 완료 대기(`_wait_for_ready`)해야 한다.
- **FR-008 (VRAM 안전 상한선 및 프리플라이트 수식 교정)**: `calculate_base_vram_mb`는 GQA 및 Q8 KV 캐시 수식을 정확히 반영하여 허위 OOM 거절을 방지해야 한다.
- **FR-009 (동시성 세마포어 및 공정 큐 제어)**: `AsyncFairQueue`와 클라이언트 레벨의 `_gpu_semaphore(max=3)`가 연동되어 동시 추론 폭주를 방어해야 한다.
- **FR-010 (좀비 프로세스 소켓 점유 방어)**: 서빙 프로세스 시작 전 이전 프로세스의 소켓 바인딩 해제 및 VRAM 해제를 검증하고, 미종료 프로세스는 `kill -9`로 강제 회수해야 한다.
- **FR-011 (Redis & L5 캐시 메모리 상한 관리)**: Redis 설정에 `maxmemory 512mb` 및 `maxmemory-policy allkeys-lru`를 적용하여 무제한 메모리 팽창을 방어해야 한다.

---

## 5. Success Criteria *(mandatory)*

1. **동적 컨텍스트 사이징 검증**: 8GB(16K~32K), 11GB(32K~48K), 12GB(64K), 24GB(128K) 가상 VRAM 주입 시 100% 정확한 동적 산출 확인.
2. **8GB 환경 무중단 안정성**: 2B (16K~32K) + BGE 2종 GPU 상주 체제에서 VRAM 피크 3.7GB 이하 유지 및 OOM 크래시 **0건**.
3. **하드코딩 잔재 0건**: 정적 코드 분석 및 전수 검색 결과 레거시 모델명/포트 하드코딩 발생 건수 **0건**.
4. **GTX 1070 최적화**: FlashAttention 경고 0건 및 Q8_0 KV Cache 적용을 통한 50% KV VRAM 절감 실측 확인.
5. **설정값 보존율 100%**: 상위 동적 설정 컨텍스트가 내부 함수 매개변수에 의해 변조되거나 덮어씌워지는 현상 **0건**.
6. **회귀 테스트 무결점**: 전사 5대 종합 회귀 테스트 스위트 100% 통과 유지.
