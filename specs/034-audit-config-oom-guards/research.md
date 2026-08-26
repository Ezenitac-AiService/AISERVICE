# Research: Unified CPU & GPU Hardware Evaluation Checklist (Pascal to Blackwell)

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 통합 CPU & GPU 하드웨어 평가 체크리스트 (Unified Hardware Checklist)

실제 배포 환경에서 시스템은 CPU와 GPU를 각각 단편적으로 보지 않고, **CPU 명령어 지원(AVX/AVX2)과 GPU 아키텍처(Pascal~Blackwell, VRAM, Tensor Core)를 종합 평가하는 통합 체크리스트**를 통해 최적의 런타임/빌드 구성을 도출합니다.

```text
======================================================================================================================================================
[평가 축 1] GPU 아키텍처 및 VRAM 평가 (GPU Evaluation Matrix)
======================================================================================================================================================
GPU 모델 (대표)       아키텍처          CUDA SM    VRAM 용량   Tensor Cores   FP16/BF16/FP8/FP4   FlashAttn-3/4   KV 양자화 권장   권장 모델 & 동적 컨텍스트
------------------------------------------------------------------------------------------------------------------------------------------------------
GTX 1070 (노말)       Pascal           SM 6.1     8 GB        없음 (None)    FP32 표준           ❌ 미지원        Q8_0 KV Cache   Qwen 3.5 2B @ 16K ~ 32K
GTX 1080 Ti          Pascal           SM 6.1     11 GB       없음 (None)    FP32 표준           ❌ 미지원        Q8_0 KV Cache   Qwen 3.5 4B @ 32K ~ 48K
RTX 2080 (노말)       Turing           SM 7.5     8 GB        1세대 텐서     FP16 네이티브       ⚠️ 생략권장      Q8_0 KV Cache   Qwen 3.5 2B @ 32K
RTX 3060 12GB        Ampere           SM 8.6     12 GB       2세대 텐서     FP16/BF16/TF32      ✅ 완전지원      Q8_0 or FP16    Qwen 3.5 4B @ 64K (초장문)
RTX 4080 (노말)       Ada Lovelace     SM 8.9     16 GB       3세대 텐서     FP16/BF16/FP8       ✅ 완전지원      FP8 / Q8_0      Qwen 3.5 4B @ 128K / 9B @ 32K
RTX 5060Ti (16GB)    Blackwell        SM 12.0    16 GB       4/5세대 텐서   FP16/BF16/FP8/FP4   ✅ FA-3/4 (TMA)  FP4 / FP8 / Q8  Qwen 3.5 4B @ 128K / 9B @ 64K
RTX 5080 (16/24G)    Blackwell        SM 12.0    16~24 GB    4/5세대 텐서   FP16/BF16/FP8/FP4   ✅ FA-3/4 (TMA)  FP4 / FP8 / Q8  Qwen 3.5 9B @ 128K (플래그십)
======================================================================================================================================================
* BGE 임베딩(706MB) + BGE 리랭커(706MB) = 1.4GB는 전 플랫폼에서 100% GPU VRAM 상주 고정.

======================================================================================================================================================
[평가 축 2] CPU 명령어 세트 평가 (CPU Evaluation Rules)
======================================================================================================================================================
CPU 명령어 세트 분류     대표 CPU 예시                           통합 체크리스트 평가 및 런타임 정책
------------------------------------------------------------------------------------------------------------------------------------------------------
1. AVX 미지원 CPU        Intel Core i7 930 (1세대 Nehalem 등)    - CPU 신경망 연산 극심한 병목 방지
                                                                 - 정책: 100% GPU VRAM 상주 (-ngl 999) 강제, CPU BLAS 연산 차단
2. AVX2 지원 CPU         Intel Core i7 7th~14th, Core Ultra 등   - 고속 토큰 직렬화 및 PCIe DMA 버퍼 전송 가속 활성화
======================================================================================================================================================
```

---

## 2. 통합 하드웨어 프로파일링 합성 엔진 (Integrated Profiling Engine)

1. **CPU & GPU 동시 감지 (`detect_hardware_capabilities()`)**:
   - `cpuinfo`를 통해 CPU의 `avx`, `avx2`, `fma` 지원 여부를 검사.
   - `pynvml`을 통해 GPU의 `compute_capability`, `total_vram_mb`, `free_vram_mb`를 검사.
2. **최적화 플래그 및 모델/컨텍스트 자동 결정**:
   - `use_flash_attn = (gpu.compute_capability >= 8.0)`
   - `force_all_gpu_layers = (not cpu.has_avx2)` (AVX 미지원 시 `-ngl 999` 강제)
   - `kv_cache_type = "fp4"` (Blackwell) / `"fp8"` (Ada) / `"q8_0"` (Pascal/Turing/Ampere)
   - `dynamic_n_ctx = calculate_dynamic_context_window(gpu.total_vram_mb, kv_cache_type)`
