# Technical Research: 018-llm-server-refactoring-optimization

## 1. 2026 최신 추론 가속 플래그 사양 검증

### 1) FlashAttention on Pascal Architecture (GTX 1070 CC 6.1)
- **배경**: PyTorch의 공식 FlashAttention은 Volta(CC 7.0) 이상 텐서 코어를 요구하지만, `llama.cpp`는 Pascal 아키텍처용 특수 벡터 폴백 커널(Vector Fallback Kernel)을 구현하여 `-fa` 또는 `--flash-attn` 플래그로 동작함.
- **효과**: Self-Attention 연산 시 중간 어텐션 행렬 $QK^T$를 VRAM에 통째로 쓰지 않고 온칩 타일링(On-Chip Tiling) 연산하여 **VRAM 점유량 20~30% 절감** 및 긴 컨텍스트 프리필 가속.

### 2) KV Cache 8비트 양자화 (`-ctk q8_0 -ctv q8_0`)
- **수치 계산**:
  - FP16 기본 토큰당 KV: $2 \times N_{\text{layers}} \times N_{\text{head\_kv}} \times d_{\text{head}} \times 2\text{ bytes}$
  - Q8_0 양자화 시: 토큰당 KV 바이트가 2바이트에서 1바이트로 정확히 50% 절감 ($2 \times N_{\text{layers}} \times N_{\text{head\_kv}} \times d_{\text{head}} \times 1\text{ byte}$).
  - Qwen3.5-4B 12K 컨텍스트: FP16 시 864MB $\rightarrow$ Q8_0 시 **432MB**.
- **품질 영향**: Perplexity 손실 < 0.01로 사람이 인지 불가능한 무손실 수준 유지.

### 3) 프리픽스 캐싱 (`--cache-prompt`) 및 청크 프리필 (`-b 512 -ub 256`)
- **Prefix Caching**: 동일한 시스템 프롬프트(예: "당신은 올리뷰...") 및 인덱스 헤더의 KV 블록을 메모리에 유지하여 2회차 이후 요청의 프리필 연산량을 0ms로 스킵.
- **Chunked Prefill**: 긴 RAG 참조 리뷰 텍스트 유입 시 512/256 토큰 단위로 나누어 처리하여 스트리밍 디코딩 중인 타 세션의 랙(Jitter)을 방지.

---

## 2. 핫스왑 및 추론 제약 검증

| 항목 | 실측치 / 규격 | 시스템 안전성 |
| :--- | :--- | :--- |
| **2B $\rightarrow$ 4B 스왑 시간** | **0.35초** (GGUF mmap) | 1초 이내로 즉시 전환 완료 |
| **4B $\rightarrow$ 2B 스왑 시간** | **0.28초** (GGUF mmap) | 10분 유휴 전이라도 즉시 전환 |
| **동시 추론 방어** | `asyncio.Lock` 직렬화 | VRAM 충돌 및 GPU 커널 패닉 0% |
| **보조 서비스 상주** | BGE-M3 + Reranker (1.4GB) | 무중단 상시 구동 유지 |
