# Feature Specification: 036-hardware-context-benchmark-expansion (실측 벤치마크 기반 하드웨어 컨텍스트 윈도우 확장, 2B/4B 하이브리드 서빙 및 고성능 플랫폼 스케일링 명세)

**Feature Branch**: `036-hardware-context-benchmark-expansion`  
**Created**: 2026-08-26  
**Status**: Draft  
**Input**: User description: "2b 상시 서빙 64k 스탠다드 / 128k 울트라, 4b 고품질 배치 32k로 하고, 이걸 최소 성능 기준으로 고성능 플렛폼에서는 vram 상황에 맞게 9b 12b 27b등 모델 카탈로그의 모델들을 서비스하게 하고, 서비스 기준점에 토큰 생성속도도 주요 요인을 해줘"

---

## 1. 개요 및 배경 (Overview & Background)

실측 벤치마크 결과, Xeon E5-2680 v4 + GTX 1070 8GB 단일 GPU 환경에서 Qwen 3.5 2B는 최대 **128K 컨텍스트(131,072 토큰)**까지 VRAM 내 로드가 가능하며, 64K 환경에서도 **TTFT ~190ms, TPS ~52 tokens/s**의 초고속 생성 성능을 달성함이 입증되었습니다. 또한 Qwen 3.5 4B 모델 역시 **32K 컨텍스트**에서 **TTFT ~238ms, TPS ~35 tokens/s**의 우수한 속도로 안정 구동됨이 확인되었습니다.

본 명세서는 이러한 실측 데이터를 시스템의 **"최소 하드웨어 성능 기준점(Minimum Baseline Platform)"**으로 공식 정의하고:
1. **Tier-1 (실시간 상시 서빙)**: Qwen 3.5 2B를 **64K Standard / 128K Ultra** 모드로 VRAM에 고정 상주시켜 제로 로드 딜레이와 50+ TPS의 반응성을 보장.
2. **Tier-2 (고품질 배치/심층 분석)**: Qwen 3.5 4B를 **32K** 모드로 온디맨드 스케줄링하여 복합 추론 품질 극대화.
3. **고성능 플랫폼 동적 스케일업(Scale-Up)**: 16GB, 24GB, 48GB+ VRAM을 갖춘 상위 플랫폼에서는 모델 카탈로그(`model_catalog.json`)에 정의된 **9B, 12B, 27B** 모델을 VRAM 용량에 맞추어 자동 선택·서빙.
4. **TPS (토큰 생성 속도) 기반 서비스 SLA 확립**: 서비스별(실시간 대화 vs 심층 배치) 요구되는 최소 생성 속도(TPS)를 모델 라우팅의 핵심 기준점으로 채택하는 것을 목적으로 합니다.

---

## Clarifications

### Session 2026-08-26
- **Q: 어제까지 4B 모델 + 16K 컨텍스트에서 OOM이 발생했던 현상과 오늘 가능해진 이유의 차이는 무엇인가?** → **A: 과거 발생한 현상은 물리적 VRAM 용량 부족(OOM)이 아니라, (1) Pascal(SM 6.1)의 FlashAttention 미지원에 따른 V-Cache 강제 양자화 에러(`llama_init_from_model: V cache quantization requires flash_attn` -> ValueError: Failed to create llama_context)와 (2) 잘못된 CLI 인자(`--cache-type-k`, `--cache-type-v`)로 인한 서브프로세스 강제 크래시였습니다. 오늘 이 플래그 불일치 버그를 교정하고 클린 VRAM 격리를 적용함에 따라, Qwen 3.5 4B(가중치 2.65GB + 16K 버퍼 1.2GB)가 8GB VRAM 내에서 ~6.15GB로 거뜬히 100% GPU 상주 가능함을 실측 확인하였습니다.**
- **Q: 2B와 4B 모델의 실제 최대 컨텍스트 윈도우, 추론 속도(TTFT/TPS), 모델 스왑 지연시간 실측값은 어떻게 되는가?** → **A: 실측 벤치마크 결과 (1) Qwen 3.5 2B는 최대 128K까지 로드 성공, 32K/64K 추론 시 TTFT 189~284ms, TPS 51.7~54.0 tokens/s의 초고속 성능을 달성. (2) Qwen 3.5 4B는 최대 48K까지 로드 성공, 16K~32K 추론 시 TTFT 231~241ms, TPS 32.9~35.0 tokens/s의 우수한 성능을 달성. (3) 모델 스왑 시간은 2B➔4B 전환 시 37.21초, 4B➔2B 전환 시 7.41초로 측정됨.**
- **Q: 상시 서빙 컨텍스트 규격과 고성능 플랫폼 스케일업 기준은 어떻게 확정하는가?** → **A: (1) 2B 상시 서빙은 64K Standard / 128K Ultra로 설정, (2) 4B 고품질 배치는 32K로 설정, (3) 현재 GTX 1070 8GB를 '최소 기준 플랫폼'으로 확립하고 상위 GPU 환경에서는 9B/12B/27B 모델을 VRAM 예산 및 TPS SLA(실시간 TPS >= 30 tokens/s)에 따라 자동 스케일업하도록 확정함.**
- **Q: 동일한 GTX 1070 8GB라도 Windows Desktop 대비 Ubuntu Headless Server 환경에서는 서빙 용량이 어떻게 달라지는가?** → **A: Windows Desktop(DWM, Explorer, IDE 등)은 약 1.34GB의 VRAM을 기본 독점 점유하여 순수 가용 VRAM이 ~6.85GB에 그치지만, Ubuntu Headless Server는 X11/GUI 오버헤드가 없어 기본 VRAM 점유가 4~15MB(거의 0)에 불과함. 따라서 Ubuntu Server에서는 동일한 GTX 1070 8GB에서도 약 +1.32GB의 순수 여유 VRAM을 추가 확보하게 되며, 이에 따라 4B 모델도 64K(65,536 tokens)까지 GPU 100% 상주가 가능해지고, 2B 128K Ultra 모드에서도 다중 동시성 처리 여유 폭이 비약적으로 증가함.**
- **Q: 모델 가중치는 Q4 양자화인데, KV 캐시는 Q8을 사용하는 것이 타당하고 올바른 설계인가?** → **A: 네, 매우 타당하며 최신 LLM 서빙 업계의 표준 권장(Sweet Spot) 설계입니다. (1) 모델 가중치(Weights)는 모델 풋프린트를 1/4로 줄이기 위해 Q4_K_M을 사용하지만, (2) KV 캐시(Attention Activations)는 추론 중 동적으로 계산되는 활성화 텐서로서, 가중치가 Q4인 상태에서 KV 캐시까지 Q4로 추가 압축하면 양자화 오차가 누적되어 장문(32K~128K)에서 환각 및 문법 붕괴 위험이 커집니다. (3) Q8_0 KV 캐시는 기본 FP16 대비 VRAM을 50% 절감하면서도 Perplexity(품질 손실)가 0.01% 미만(Lossless)을 유지하므로, 'Q4 가중치 + Q8 KV 캐시' 조합이 메모리 절감과 한국어 생성 품질 간의 가장 완벽한 균형점을 제공합니다.**

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - Qwen 3.5 2B 상시 서빙 (64K Standard / 128K Ultra) 및 초고속 토큰 생성 (Priority: P1)

챗봇(ChatA, ChatB) 사용자는 Qwen 3.5 2B 상시 서빙 인스턴스를 통해 최대 65,536토큰(표준) 및 131,072토큰(울트라)의 방대한 대화 이력과 리뷰 전문을 단일 턴에 주입하더라도, 0.2초 이내(TTFT)에 출력이 시작되고 초당 50토큰 이상의 속도(TPS)로 끊김 없는 실시간 답변을 수신해야 합니다.

- **Why this priority**: 서비스의 기본 사용자 경험(UX)과 직결되며, 8GB GPU 환경에서 제로 로드 대기 시간과 초고속 응답성을 동시에 보장하는 핵심 서비스이기 때문입니다.
- **Independent Test**: `qwen3.5-2b` 모델을 `n_ctx=65536` 및 `n_ctx=131072`로 상시 가동하고 대화형 스트리밍 요청을 전송하여 TTFT $\le 300\text{ms}$, TPS $\ge 45\text{ tokens/s}$를 독립 검증합니다.

**Acceptance Scenarios**:
1. **Given** 2B 모델이 64K Standard 모드로 상주 중일 때, **When** 10턴의 대화 기록 및 20개 리뷰(약 30,000자)가 주입되면, **Then** VRAM 5.0GB 이하를 유지하며 0.3초 이내에 스트리밍이 시작되고 50 tokens/s 이상의 속도로 완결되어야 합니다.
2. **Given** 128K Ultra 모드가 활성화되었을 때, **When** 최대 10만 토큰의 대규모 텍스트가 전달되면, **Then** OOM 없이 정상적으로 100% 레이어 GPU 가속 추론이 수행되어야 합니다.

---

### User Story 2 - Qwen 3.5 4B 고품질 배치 32K 서빙 및 지능형 스왑 (Priority: P2)

PILOS 감성 분석 파이프라인 또는 관리자 심층 리포트 생성 시, 시스템은 Qwen 3.5 4B 모델을 **32K 컨텍스트**로 온디맨드 스위칭하여 일일 뉴스 50건 전체를 35 tokens/s의 안정적인 속도로 심층 분석하고, 작업 완료 후 다시 2B 상시 모드로 복귀해야 합니다.

- **Why this priority**: 복합 추론 및 한국어 심층 요약 능력이 뛰어난 4B 모델을 8GB VRAM 한도 내에서 안전하게 활용하기 위함입니다.
- **Independent Test**: 4B 모델을 `n_ctx=32768`로 스왑 로드하여 뉴스 50건 분석 완료 후 다시 2B로 자동 복귀하는 E2E 수명주기를 검증합니다.

**Acceptance Scenarios**:
1. **Given** 일일 감성 지수 배치 작업이 시작될 때, **When** 게이트웨이가 2B에서 4B(32K)로 전환하면, **Then** 38초 이내에 로드가 완료되고 TPS 30+ tokens/s로 고품질 리포트가 생성되어야 합니다.
2. **Given** 배치 작업이 완료되면, **When** 대기 타임아웃(예: 60초)이 경과했을 때, **Then** 4B 인스턴스를 언로드하고 2B 상시 모델(64K)로 8초 이내에 자동 복귀해야 합니다.

---

### User Story 3 - 고성능 플랫폼 스케일업(9B, 12B, 27B) 및 TPS 기반 모델 라우팅 (Priority: P3)

시스템 관리자가 16GB, 24GB, 48GB+ 이상의 고성능 GPU(RTX 3090, 4090, A100 등)로 서버를 마이그레이션하거나 증설할 경우, 게이트웨이는 하드웨어 VRAM과 TPS 기준점을 바탕으로 모델 카탈로그(`model_catalog.json`)의 상위 모델(9B, 12B, 27B)을 자동으로 프로파일링하여 최적의 모델을 배치해야 합니다.

- **Why this priority**: 단일 코드베이스로 8GB 최소 사양부터 80GB 엔터프라이즈 사양까지 무설정 자동 적응형 서빙을 실현하기 위함입니다.
- **Independent Test**: 가상 VRAM(16GB, 24GB, 48GB) 및 TPS 프로파일을 시뮬레이션하여 9B/12B/27B 모델이 적절한 컨텍스트와 함께 자동 선택되는지 검증합니다.

**Acceptance Scenarios**:
1. **Given** VRAM 16GB~24GB 환경이 감지되었을 때, **When** 하드웨어 프로파일러가 실행되면, **Then** Qwen 3.5 9B 또는 Gemma 4 12B가 권장 모델로 자동 매핑되고 TPS $\ge 30\text{ tokens/s}$를 만족하는 컨텍스트(32K~64K)가 설정되어야 합니다.
2. **Given** VRAM 48GB 이상 환경이 감지되었을 때, **When** 프로파일러가 실행되면, **Then** Qwen 3.6 27B / 35B-A3B 모델이 고품질 서빙 타겟으로 등록되어야 합니다.

---

### Edge Cases

- **EC-001 (TPS SLA 미달 시 자동 강등)**: 고사양 모델(예: 4B/9B) 실행 중 CPU 병목이나 동시 요청으로 인해 TPS가 20 tokens/s 미만으로 지속 저하될 경우, 실시간 서비스는 2B 상시 모델로 자동 폴백.
- **EC-002 (스왑 중 인바운드 실시간 요청 인입)**: 4B 배치 실행 도중 B-Team 챗봇 질의가 유입되면, FairQueue가 우선순위(Priority Queue)를 적용하여 배치 작업을 잠시 일시정지하거나 Fast 2B 인스턴스로 분기 처리.
- **EC-003 (초대용량 128K 초과 프롬프트)**: 주입 데이터가 131,072 토큰을 초과하는 경우, 계층형 메모리 요약([Turn N] 롤업)을 우선 적용하여 중요 문맥을 128K 이내로 압축.

---

## 3. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 Qwen 3.5 2B 모델을 기본 상시 서빙(Resident Model)으로 설정하고, **64K Standard (65,536 tokens)** 및 **128K Ultra (131,072 tokens)** 컨텍스트 윈도우를 공식 지원해야 한다.
- **FR-002**: 시스템은 Qwen 3.5 4B 모델에 대해 **32K (32,768 tokens)** 고품질 배치/심층 분석 프로파일을 공식 지원해야 한다.
- **FR-003**: 시스템은 Xeon E5-2680 v4 + GTX 1070 8GB를 **최소 하드웨어 기준점(Minimum Baseline)**으로 고정하고, 해당 하드웨어에서 2B(64K/128K) 및 4B(32K)의 안전 구동을 보장해야 한다.
- **FR-004**: `gpu_detector.py`의 `calculate_3axis_dynamic_context` 및 모델 매핑 로직은 VRAM 용량에 따라 모델 카탈로그(`model_catalog.json`)의 상위 모델들을 자동 선별해야 한다:
  * $\text{VRAM} < 11\text{GB}$ (GTX 1070 8GB): 2B (64K/128K) 상시, 4B (32K) 온디맨드
  * $11\text{GB} \le \text{VRAM} < 20\text{GB}$ (RTX 3060 12GB, 4070 16GB): 4B/9B 상시 (32K~64K)
  * $20\text{GB} \le \text{VRAM} < 40\text{GB}$ (RTX 3090/4090 24GB): 9B/12B 상시 (64K~128K)
  * $\text{VRAM} \ge 40\text{GB}$ (A100, H100): 27B / 35B-A3B 상시 (128K)
- **FR-005**: 시스템은 **토큰 생성 속도(TPS)**를 서비스 품질 기준점(SLA)으로 채택하여:
  * 실시간 대화 서비스(ChatA/ChatB): 최소 $\text{TPS} \ge 30\text{ tokens/s}$ (목표 $50+\text{ tokens/s}$) 보장
  * 배치/리포트 서비스(PILOS): 최소 $\text{TPS} \ge 20\text{ tokens/s}$ (목표 $30+\text{ tokens/s}$) 보장
- **FR-006**: B-Team 챗봇 코어(`oliview_core/config.py`)는 3-Tier 컨텍스트 프로파일을 `64K_STANDARD` 및 `128K_ULTRA`로 확장하여 검색 리뷰 및 심층 대화 이력 인용 폭을 극대화해야 한다.
- **FR-007**: Pascal GPU(GTX 1070)에 대해 FlashAttention 미지원에 따른 V-Cache 양자화 생략 로직을 유지하고, Ampere 이상 상위 GPU에서는 FlashAttention + Full Quantized KV Cache를 자동 활성화해야 한다.

---

## 4. Key Entities *(include if feature involves data)*

- **HardwarePlatformTier**:
  - `tier_name`: 플랫폼 티어 (`BASELINE_8GB`, `MID_16GB_24GB`, `HIGH_48GB_PLUS`)
  - `resident_model_id`: 상시 서빙 모델 (`qwen3.5-2b`, `qwen3.5-9b`, `qwen3.6-27b`)
  - `standard_n_ctx`: 표준 컨텍스트 윈도우 (65,536 ~ 131,072)
  - `batch_model_id`: 배치 고품질 모델 (`qwen3.5-4b`, `gemma4-12b`, `qwen3.6-35b-a3b`)
  - `min_target_tps`: 보장 최소 생성 속도 (30.0 ~ 50.0 tokens/s)
- **ModelCatalogProfile**:
  - `model_id`: 모델 식별자 (예: `qwen3.5-2b`, `qwen3.5-4b`, `qwen3.5-9b`, `gemma4-12b`, `qwen3.6-27b`)
  - `min_vram_required_mb`: 최소 필요 VRAM
  - `supported_n_ctx_levels`: 지원 컨텍스트 배열 (`[16384, 32768, 65536, 131072]`)
  - `measured_tps`: 실측 토큰 생성 속도

---

## 5. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (실시간 반응성)**: Qwen 3.5 2B @ 64K 환경에서 첫 토큰 생성 시간(TTFT) 300ms 이하, 생성 속도(TPS) 50 tokens/s 이상을 달성해야 한다.
- **SC-002 (대용량 컨텍스트)**: Qwen 3.5 2B @ 128K 및 Qwen 3.5 4B @ 32K 환경에서 100% 레이어 GPU 오프로드 및 무결점 완결을 달성해야 한다.
- **SC-003 (배치 추론 효율)**: Qwen 3.5 4B @ 32K 환경에서 50건 뉴스 분석 시 TPS 30 tokens/s 이상을 유지해야 한다.
- **SC-004 (플랫폼 자동 스케일업)**: 8GB부터 80GB까지 GPU VRAM 크기별 모델 및 컨텍스트 매핑 단위 테스트가 100% 통과해야 한다.
- **SC-005 (전사 회귀 검증)**: B-Team 챗봇 및 PILOS의 전사 회귀 테스트 스위트가 64K Standard 환경에서 100% 통과해야 한다.

---

## 6. Assumptions

- 최소 기준 장비는 Intel Xeon E5-2680 v4 + NVIDIA GeForce GTX 1070 8GB 단일 GPU이다.
- 모델 카탈로그(`model_catalog.json`)에 등록된 모델들(2B, 4B, 9B, 12B, 27B, 35B)은 GGUF Q4_K_M 양자화 규격을 기본으로 한다.
- BGE-M3 임베딩(8090) 및 Reranker(8091)는 GPU VRAM에 기본 상주(약 1.6GB 예약)하여 동작한다.
- 고성능 플랫폼 감지 시 상위 모델 파일이 로컬에 부재한 경우, 게이트웨이의 자동 다운로더(`ModelDownloader`)가 HuggingFace에서 자동 페치하거나 사전 준비된 모델을 매핑한다.
