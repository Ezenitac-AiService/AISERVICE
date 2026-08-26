# Research: 5-Tier GPU Architecture Specs & Hardware-Aware Optimization

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 5대 타겟 GPU 세대별 불변 하드웨어 스펙 매트릭스 (Immutable GPU Hardware Matrix)

새로운 GPU 세대가 출시되지 않는 한 본 하드웨어 스펙 및 지원 기술 매트릭스는 영구 불변(Immutable)의 단일 진실 소스(SSOT)로 동작합니다.

```text
==========================================================================================================================================
GPU 모델명            아키텍처      CUDA SM   VRAM 용량   Tensor Cores   FP16 속도   BF16   FP8    FlashAttn-3   KV 양자화 권장   llama-server 권장 플래그
==========================================================================================================================================
1. GTX 1070 (노말)    Pascal       SM 6.1    8 GB        없음 (None)    1:64 (느림) ❌     ❌     ❌ 미지원      Q8_0 KV Cache   --cache-type-k q8_0 --cache-type-v q8_0 -ngl 999
2. GTX 1080 Ti       Pascal       SM 6.1    11 GB       없음 (None)    1:64 (느림) ❌     ❌     ❌ 미지원      Q8_0 KV Cache   --cache-type-k q8_0 --cache-type-v q8_0 -ngl 999
3. RTX 2080 (노말)    Turing       SM 7.5    8 GB        1세대 텐서     1:1 (네이티브) ❌   ❌     ⚠️ 제한적     Q8_0 KV Cache   --cache-type-k q8_0 --cache-type-v q8_0 -ngl 999
4. RTX 3060 (12GB)   Ampere       SM 8.6    12 GB       2세대 텐서     2:1 (초고속)   ✅     ❌     ✅ 완전지원    Q8_0 or FP16    --flash_attn True --cache-type-k q8_0 -ngl 999
5. RTX 4080 (노말)    Ada Lovelace SM 8.9    16 GB       3세대 텐서     4:1 (극초고속) ✅     ✅     ✅ 완전지원    FP8 / Q8_0      --flash_attn True --cache-type-k fp8 -ngl 999
==========================================================================================================================================
```

---

## 2. 호스트 CPU (Intel Core i7 930) 제약과 100% GPU Offloading 원칙

* **Host CPU 특성**: Intel Core i7 930 (1세대 Nehalem, SSE4.2 지원, **AVX/AVX2/AVX-512 미지원**)
* **결론 및 원칙**:
  - AVX2가 없는 레거시 CPU에서 트랜스포머 신경망(LLM, BGE 임베딩, BGE 리랭커)을 CPU로 연산하면 수 초~수십 초의 치명적 병목이 발생함.
  - 따라서 모든 신경망 연산은 **100% GPU VRAM 상주 (`-ngl 999`)**로 고정하고, CPU는 순수 IO/스트리밍/룰게이트만 전담함.

---

## 3. 세대별 최적 서빙 전략 및 컨텍스트 매핑

1. **Pascal (GTX 1070 8GB / GTX 1080Ti 11GB)**:
   - SM 6.1: FlashAttention 명령어 파이프라인이 없으므로 `--flash_attn` 옵션은 생략하고 **Q8_0 KV Cache**로 VRAM 50% 절감.
   - GTX 1070: `2B @ 16K~32K` (VRAM 3.7GB 이하 유지).
   - GTX 1080Ti: `4B @ 32K~48K` (11GB VRAM 활용).
2. **Turing (RTX 2080 8GB)**:
   - SM 7.5: 1세대 텐서 코어(FP16 네이티브) 지원, `2B @ 32K` 고속 FP16 연산.
3. **Ampere (RTX 3060 12GB)**:
   - SM 8.6: FlashAttention-2/3 완전 지원, `4B @ 64K` 초장문 네이티브 상주 서빙.
4. **Ada Lovelace (RTX 4080 16GB)**:
   - SM 8.9: Transformer Engine & FlashAttention-3 완전 지원, `4B @ 128K` 또는 `9B @ 32K` 플래그십 서빙.
