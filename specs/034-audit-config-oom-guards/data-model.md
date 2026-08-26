# Data Model: 3-Axis Decoupled Hardware Evaluation Engine

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 3대 직교 독립 하드웨어 평가 데이터 모델 (Pydantic v2)

```python
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class GpuArchitectureEnum(str, Enum):
    PASCAL_SM61 = "pascal_sm61"          # SM 6.1 (GTX 1070 8GB, GTX 1080 Ti 11GB 등)
    TURING_SM75 = "turing_sm75"          # SM 7.5 (RTX 2060 6/12GB, RTX 2080 8GB 등)
    AMPERE_SM86 = "ampere_sm86"          # SM 8.6 (RTX 3060 12GB, RTX 3070 8GB, RTX 3080 등)
    ADA_SM89 = "ada_sm89"                # SM 8.9 (RTX 4060 8GB, RTX 4070 12GB, RTX 4080 16GB 등)
    BLACKWELL_SM120 = "blackwell_sm120"  # SM 12.0 (RTX 5060 8GB, RTX 5060 Ti 16GB, RTX 5080 16/24GB 등)
    UNKNOWN = "unknown"


class CpuArchitectureFeatures(BaseModel):
    """[축 3] 독립적 CPU 명령어 세트 특성"""
    cpu_model_name: str = Field(..., description="CPU 모델명 (예: Intel Core i7 930)")
    has_avx: bool = Field(default=False, description="AVX 지원 여부")
    has_avx2: bool = Field(default=False, description="AVX2 지원 여부")
    has_fma: bool = Field(default=False, description="FMA3 지원 여부")
    requires_gpu_only: bool = Field(default=False, description="AVX 미지원으로 100% GPU VRAM 상주(-ngl 999) 강제 여부")


class GpuArchitectureFeatures(BaseModel):
    """[축 1] 독립적 GPU 아키텍처 세대별 불변 하드웨어 특성 (VRAM 용량과 무관)"""
    architecture_name: str = Field(..., description="아키텍처명 (Pascal, Turing, Ampere, Ada, Blackwell)")
    compute_capability: float = Field(..., description="CUDA Compute Capability (6.1, 7.5, 8.6, 8.9, 12.0)")
    has_tensor_cores: bool = Field(..., description="텐서 코어 탑재 여부")
    supports_fp16_native: bool = Field(..., description="FP16 1:1 고속 연산 지원 여부")
    supports_bf16_native: bool = Field(..., description="BF16 연산 지원 여부")
    supports_fp8_native: bool = Field(..., description="FP8 (Transformer Engine) 연산 지원 여부")
    supports_fp4_native: bool = Field(default=False, description="FP4 (Blackwell NVFP4) 연산 지원 여부")
    supports_flash_attn: bool = Field(..., description="FlashAttention-3/4 지원 여부 (SM >= 8.0)")
    recommended_kv_type: str = Field(default="q8_0", description="권장 KV Cache 양자화 타입 (q8_0, fp16, fp8, fp4)")


class DynamicHardwareProfile(BaseModel):
    """[축 1 + 축 2 + 축 3] 3대 직교 실측 합성 프로파일"""
    device_name: str = Field(..., description="GPU 장치명 (예: NVIDIA GeForce RTX 4060)")
    compute_capability: float = Field(..., description="CUDA Compute Capability")
    gpu_features: GpuArchitectureFeatures = Field(..., description="GPU 아키텍처 특성")
    cpu_features: CpuArchitectureFeatures = Field(..., description="CPU 명령어 특성")
    total_vram_mb: int = Field(..., description="물리 VRAM 전체 용량 (MB)")
    free_vram_mb: int = Field(..., description="현재 가용 VRAM 용량 (MB)")
    recommended_model: str = Field(..., description="VRAM 및 KV 타입 기반 최적 상주 모델 (qwen3.5-2b / 4b / 9b)")
    dynamic_n_ctx: int = Field(..., description="VRAM 예산 및 KV 바이트 기반 동적 산출 최대 컨텍스트 윈도우")
    use_q8_kv: bool = Field(default=True, description="Q8_0 KV Cache 활성화 여부")
    use_fp8_kv: bool = Field(default=False, description="FP8 KV Cache 활성화 여부")
    use_fp4_kv: bool = Field(default=False, description="FP4 KV Cache 활성화 여부")
    use_flash_attn: bool = Field(default=False, description="FlashAttention 활성화 여부")
    force_all_gpu_layers: bool = Field(default=True, description="-ngl 999 100% GPU 강제 여부")
```
