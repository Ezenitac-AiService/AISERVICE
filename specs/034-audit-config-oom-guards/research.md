# Research: 6-Tier GPU Architecture Specs & Hardware-Aware Optimization (Pascal to Blackwell)

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 6대 타겟 GPU 세대별 불변 하드웨어 스펙 매트릭스 (Pascal $\rightarrow$ Blackwell)

새로운 세대(RTX 6000번대 이후)가 나오기 전까지 본 체크리스트는 시스템 전반의 영구 불변(Immutable) 단일 진실 소스(SSOT)로 동작합니다.

```text
======================================================================================================================================================
GPU 모델명            아키텍처          CUDA SM    VRAM 용량   Tensor Cores   FP16/BF16/FP8/FP4   FlashAttn-3/4   KV 양자화 권장   권장 모델 & 동적 컨텍스트
======================================================================================================================================================
1. GTX 1070 (노말)    Pascal           SM 6.1     8 GB        없음 (None)    FP32 표준           ❌ 미지원        Q8_0 KV Cache   Qwen 3.5 2B @ 16K ~ 32K
2. GTX 1080 Ti       Pascal           SM 6.1     11 GB       없음 (None)    FP32 표준           ❌ 미지원        Q8_0 KV Cache   Qwen 3.5 4B @ 32K ~ 48K
3. RTX 2080 (노말)    Turing           SM 7.5     8 GB        1세대 텐서     FP16 네이티브       ⚠️ 생략권장      Q8_0 KV Cache   Qwen 3.5 2B @ 32K
4. RTX 3060 (12GB)   Ampere           SM 8.6     12 GB       2세대 텐서     FP16/BF16/TF32      ✅ 완전지원      Q8_0 or FP16    Qwen 3.5 4B @ 64K (초장문)
5. RTX 4080 (노말)    Ada Lovelace     SM 8.9     16 GB       3세대 텐서     FP16/BF16/FP8       ✅ 완전지원      FP8 / Q8_0      Qwen 3.5 4B @ 128K / 9B @ 32K
6. RTX 5060Ti (16GB) Blackwell        SM 12.0    16 GB       4/5세대 텐서   FP16/BF16/FP8/FP4   ✅ FA-3/4 (TMA)  FP4 / FP8 / Q8  Qwen 3.5 4B @ 128K / 9B @ 64K
7. RTX 5080 (16/24G) Blackwell        SM 12.0    16~24 GB    4/5세대 텐서   FP16/BF16/FP8/FP4   ✅ FA-3/4 (TMA)  FP4 / FP8 / Q8  Qwen 3.5 9B @ 128K (플래그십)
======================================================================================================================================================
```

---

## 2. Blackwell 아키텍처 (RTX 5000 Series) 특성 및 미래 확장성

1. **Microscaling FP4 (NVFP4) 및 2세대 Transformer Engine**:
   - RTX 5000번대(SM 12.0)는 FP4 가속을 지원하여 KV 캐시 메모리를 FP16 대비 **75% 절감** 가능.
   - 16GB VRAM(5060 Ti)에서도 9B 모델을 64K~128K 초장문 컨텍스트로 여유롭게 상주 서빙 가능.
2. **Tensor Memory Accelerator (TMA) & FlashAttention-4**:
   - 하드웨어 TMA 가속을 통해 FlashAttention-3/4의 연산 효율이 극대화되어 긴 컨텍스트 추론 지연시간이 대폭 감소.

---

## 3. 호스트 CPU (Intel Core i7 930) 제약과 100% GPU Offload 원칙

* Host CPU는 1세대 Nehalem(AVX 미지원)이므로, 6대 GPU 플랫폼 전역에서 모든 신경망 연산은 **100% GPU VRAM 상주 (`-ngl 999`)**로 강제 고정함.
