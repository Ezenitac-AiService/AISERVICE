# Research & Technical Decisions: 036-hardware-context-benchmark-expansion

**Feature**: [spec.md](./spec.md)  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 하드웨어 실측 벤치마크 및 VRAM 안전 마진 분석 (Hardware Benchmark Analysis)

### 1) 결정 (Decision)
- **Tier-1 (실시간 대화 상시 서빙)**: `Qwen 3.5 2B`를 기본 컨텍스트 **64K Standard (65,536 tokens)**, 최대 **128K Ultra (131,072 tokens)**로 GPU VRAM에 고정 상주.
- **Tier-2 (고품질 일괄 배치 분석)**: `Qwen 3.5 4B`를 **32K (32,768 tokens)** 모드로 온디맨드 스케줄링.
- **GTX 1070 8GB VRAM 분할 예산 (Windows Desktop 환경)**:
  * OS / Desktop GUI 점유: ~1,350 MiB
  * 보조 모델 상주 (BGE-M3 8090 + Reranker 8091): ~1,600 MiB
  * 2B (64K) 모델 가중치 + Compute Buffer: $1,211 + 750 = 1,961\text{ MiB}$
  * **2B 64K 가동 시 총 VRAM**: $1350 + 1600 + 1961 \approx \mathbf{4,911\text{ MiB}}$ (잔여 안전 마진: **3,281 MiB / 40.1%**)
  * 4B (32K) 모델 가중치 + Compute Buffer: $2,740 + 1,400 = 4,140\text{ MiB}$
  * **4B 32K 가동 시 총 VRAM**: $1350 + 1600 + 4140 \approx \mathbf{7,090\text{ MiB}}$ (잔여 안전 마진: **1,102 MiB / 13.5%**)

### 2) 근거 (Rationale)
- 2B 모델 실측 결과: 64K 환경에서 TTFT ~190ms, TPS ~52 tokens/s로 실시간 UX 목표(TPS $\ge 30$)를 초과 달성.
- 4B 모델 실측 결과: 32K 환경에서 TTFT ~238ms, TPS ~35 tokens/s로 고품질 뉴스 요약 및 감성 분석 배치에 최적.
- 스왑 지연시간 실측치(2B➔4B 37.2초, 4B➔2B 7.4초)에 따라 실시간 챗봇은 2B 상시 서빙을 유지하고 배치는 백그라운드 스케줄러로 처리하는 2-Tier 분리가 가장 합리적임.

### 3) 검토된 대안 (Alternatives Considered)
- **대안 A (4B 상시 서빙 + 2B 배제)**: 4B 로드 시 37초가 소요되고 동시 요청 시 VRAM 여유 마진이 1.1GB로 타이트하여, 실시간 대화 UX 저하 위험으로 기각.
- **대안 B (2B 16K 고정 유지)**: 2B GQA의 강력한 압축 효율을 방치하고 사용자 리뷰 인용 한도를 6개로 제한하는 낭비이므로 기각.

---

## 2. 양자화 및 어텐션 커널 표준 (W4A8 & FlashAttention Fallback)

### 1) 결정 (Decision)
- **모델 가중치**: `Q4_K_M` GGUF 포맷 표준 유지.
- **KV 캐시**:
  * **Pascal (GTX 1070, SM 6.1)**: FlashAttention 미지원에 따라 `type_v` 강제 양자화를 생략하고 기본 버퍼 + K-Cache Q8을 적용하여 `Failed to create llama_context` 크래시 원천 차단.
  * **Ampere/Ada/Blackwell (SM 8.0+)**: FlashAttention + Full Q8_0 / FP8 KV Cache 자동 활성화.

### 2) 근거 (Rationale)
- 가중치가 Q4인 상태에서 KV 캐시까지 Q4로 추가 압축하면 장문(32K~128K)에서 양자화 오차 곱셈 누적으로 인한 환각이 급증함.
- Q8 KV 캐시는 FP16 대비 VRAM을 50% 절감하면서도 Perplexity 손실이 0.01% 미만(Lossless)임.

---

## 3. 고성능 플랫폼 스케일업 매트릭스 및 TPS SLA 라우팅

### 1) 결정 (Decision)
- `gpu_detector.py`의 `calculate_3axis_dynamic_context` 및 `LlamaServerProcessManager`가 실시간 VRAM 텔레메트리를 통해 모델 카탈로그(`model_catalog.json`)에서 최적 모델을 자동 매핑:
  * **$\text{VRAM} < 11\text{GB}$ (GTX 1070 8GB)**: 2B (64K/128K) 상시, 4B (32K) 온디맨드
  * **$11\text{GB} \le \text{VRAM} < 20\text{GB}$ (RTX 3060 12GB, 4070 16GB)**: 4B/9B 상시 (32K~64K)
  * **$20\text{GB} \le \text{VRAM} < 40\text{GB}$ (RTX 3090/4090 24GB)**: 9B/12B 상시 (64K~128K)
  * **$\text{VRAM} \ge 40\text{GB}$ (A100/H100)**: 27B / 35B-A3B 상시 (128K)
- **TPS SLA 가드**:
  * 실시간 대화: 최소 TPS $\ge 30\text{ tokens/s}$ (미달 시 하위 모델로 자동 폴백)
  * 배치 분석: 최소 TPS $\ge 20\text{ tokens/s}$

### 2) 근거 (Rationale)
- 하드웨어 업그레이드 시 코드 수정 없이 VRAM과 속도 기준점에 따라 자동으로 최상위 모델을 선택·서빙하는 완전 자동 적응형 아키텍처 실현.
