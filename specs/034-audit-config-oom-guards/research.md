# Research: 6-Tier CPU-GPU Hardware Topology & Capability Specs

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 6대 CPU-GPU 페어링 하드웨어 토폴로지 매트릭스 (Hardware Pairing Matrix)

각 타겟 플랫폼은 GPU 세대에 맞춰 **GPU 병목이 발생하지 않는 최적 세대의 Intel CPU**와 페어링되어 구축·운영됩니다.

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
```

---

## 2. CPU 명령어 자동 감지 및 빌드/런타임 적응형 최적화

1. **Tier 1 (GTX 1070 + i7 930 특화 처리)**:
   - `cpu_detector.py`가 `avx2` 부재를 감지하면, 트랜스포머 레이어가 CPU로 누수되지 않도록 `-ngl 999`를 강제하고 CPU 양자화/BLAS 부하를 차단.
   - 바이너리 빌드 옵션: `LLAMA_AVX=OFF LLAMA_AVX2=OFF LLAMA_FMA=OFF LLAMA_CUDA=ON`.
2. **Tier 2 ~ 6 (현대적 Intel CPU + 상위 GPU 특화 처리)**:
   - `avx2` 및 `fma` 지원을 감지하여 고속 토큰 전처리 및 호스트-디바이스 DMA 고속 전송 활용.
   - 바이너리 빌드 옵션: `LLAMA_AVX2=ON LLAMA_FMA=ON LLAMA_CUDA=ON`.
