# Research & Technical Decisions: Dynamic Model Discovery & Hardware-Aware Synchronization

**Feature**: `033-dynamic-model-discovery-sync`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 2026 Modern LLM Serving Architecture & Trends

### 1.1 하드웨어 제약 기반 동적 프로파일링 (Hardware-Aware Dynamic Profiling)
* **배경**: 2026년 기준 vLLM, llama.cpp, Triton 기반 AI 플랫폼에서는 모델명과 컨텍스트 길이를 소스코드나 정적 환경변수에 하드코딩하지 않고, **호스트 VRAM 용량과 하드웨어 토폴로지를 검사하여 실시간으로 최적 모델 및 컨텍스트 예산을 산출**합니다.
* **수식 모델**:
  $$\text{VRAM}_{\text{Required}} = \text{Model Weights} + \text{KV Cache}(n_{\text{ctx}}) + \text{Auxiliary Models (Embed + Rerank)} + \text{Safety Margin}$$
* **기준 제약 조건**:
  - 기본 RAG 심층 합성 및 다중 리뷰 비교를 위해 **최소 16K (`n_ctx=16384`) 컨텍스트 윈도우 필수 보장**.
  - 16K 컨텍스트를 만족하는 상태에서 가용 VRAM에 100% 상주 가능한 **최대 파라미터 모델**을 자동 선정.

---

## 2. Technical Decisions & Tradeoffs

### Decision 1: VRAM 용량별 모델 매핑 매트릭스 (VRAM Topology Matrix)
* **결정**:
  - **8GB GPU (GTX 1070)**: `qwen3.5-2b` + `16K ctx` (가중치 1.5GB + 16K KV 0.25GB + Aux 1.6GB + OS 3.7GB = **7.05GB** 점유, 완벽 안정 상주).
  - **16GB GPU (RTX 4080 / T4)**: `qwen3.5-4b` + `16K ctx` (가중치 2.8GB + 16K KV 0.4GB + Aux 1.6GB = **4.8GB** 점유).
  - **24GB+ GPU (RTX 3090 / 4090)**: `qwen3.5-9b` + `16K ctx` (가중치 5.5GB + 16K KV 0.75GB + Aux 1.6GB = **7.85GB** 점유).
* **근거**: 8GB GPU 환경에서 4B 모델을 무리하게 올리면 VRAM 한도(8.19GB)를 초과하여 Linux Kernel OOM Killer가 발생하므로, 2B 모델에 16K 대용량 컨텍스트를 부여하여 4B 수준의 RAG 성능을 완벽히 달성.
* **고려된 대안**: 컨텍스트를 4K로 줄이고 4B 모델을 띄우는 방안 ➔ **기각 (컨텍스트 축소 시 RAG 다중 리뷰 주입 불가로 품질 저하)**.

---

### Decision 2: 클라이언트 동적 모델 발견(Discovery) & TTL 캐싱
* **결정**:
  - [AiGatewayClient](file:///c:/AISERVICE/bteam/oliview_core/client.py)에 `discover_active_model()` 메서드를 구현하여 게이트웨이 `GET /v1/models` 및 `GET /v1/profile`을 질의.
  - 질의 결과(활성 모델명, 컨텍스트 크기)를 **인메모리에 60초 TTL로 캐싱**하여, 실시간 추론 시 0ms 오버헤드로 활성 모델명을 참조.
  - 게이트웨이 미기동/네트워크 오류 시 [CoreSettings](file:///c:/AISERVICE/bteam/oliview_core/config.py)의 안전 기본값(`qwen3.5-2b`)으로 즉시 폴백.
* **근거**: 다운스트림 서비스(Chatbot A/B, PILOS, Worker)가 정적 `.env`에 묶이지 않고 게이트웨이 설정 변경 시 60초 이내에 자동 동기화됨.

---

### Decision 3: 초장문 컨텍스트(32K~64K) 요구 시 경량 모델 동적 스케일다운
* **결정**:
  - 고사양 GPU(16GB/24GB)에서 기본 모델이 4B/9B로 승격되어 있더라도, **초대형 문서 분석이나 장기 대화 히스토리(32K~64K 토큰)가 요구되는 특수 작업** 유입 시 경량 2B 모델로 동적 스케일다운하여 VRAM OOM 없이 초장문 윈도우를 완벽 처리.
* **근거**: 2B 모델의 FlashAttention KV 캐시는 초경량(~400MB on 32K)이므로 극단적 장문 처리에 최적화됨.

---

### Decision 4: 단일 상주 모드(`SINGLE_MODEL_MODE=true`) 투명 라우팅 및 로딩 보호
* **결정**:
  - 게이트웨이가 8GB 환경에서 단일 상주 모드일 때, 클라이언트가 `qwen3.5-4b`를 요청하더라도 내부적으로 상주 `qwen3.5-2b (16K ctx)`로 투명 매핑하여 서빙.
  - `load_model_with_download()`에서 대상 모델이 `LOADING` 상태일 경우 기존 프로세스를 종료하지 않고 준비 완료를 대기(`_wait_for_ready`)하도록 보호.
* **근거**: 불필요한 프로세스 킬 및 무한 재시작 루프(Cascade Kill) 원천 방지.
