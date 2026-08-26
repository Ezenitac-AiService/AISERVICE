# Data Model: 6-Tier GPU Architecture Specs (Pascal to Blackwell)

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 6대 GPU 세대 및 아키텍처 특성 스키마 (Pydantic v2)

```python
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class GpuArchitectureEnum(str, Enum):
    PASCAL_SM61 = "pascal_sm61"          # GTX 1070 (8GB), GTX 1080 Ti (11GB)
    TURING_SM75 = "turing_sm75"          # RTX 2080 (8GB)
    AMPERE_SM86 = "ampere_sm86"          # RTX 3060 (12GB)
    ADA_SM89 = "ada_sm89"                # RTX 4080 (16GB)
    BLACKWELL_SM120 = "blackwell_sm120"  # RTX 5060 Ti (16GB), RTX 5080 (16/24GB), RTX 5090 (32GB)
    UNKNOWN = "unknown"


class GpuArchitectureFeatures(BaseModel):
    """GPU 아키텍처 세대별 불변 하드웨어 특성 스펙"""
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
    """실시간 물리 GPU VRAM 및 Compute Capability 실측 기반 프로파일"""
    device_name: str = Field(..., description="GPU 장치명 (예: NVIDIA GeForce GTX 1070)")
    compute_capability: float = Field(..., description="CUDA Compute Capability")
    architecture: GpuArchitectureEnum = Field(..., description="판별된 GPU 아키텍처")
    features: GpuArchitectureFeatures = Field(..., description="아키텍처 세부 기능 스펙")
    total_vram_mb: int = Field(..., description="전체 물리 VRAM (MB)")
    free_vram_mb: int = Field(..., description="현재 가용 VRAM (MB)")
    recommended_model: str = Field(..., description="VRAM 최적 추천 상주 모델 (qwen3.5-2b / 4b / 9b)")
    dynamic_n_ctx: int = Field(..., description="VRAM 예산 기반 동적 산출 최대 컨텍스트 윈도우")
    use_q8_kv: bool = Field(default=True, description="Q8_0 KV Cache 활성화 여부")
    use_flash_attn: bool = Field(default=False, description="FlashAttention 활성화 여부")
```

---

## 2. 6대 타겟 GPU 아키텍처 룩업 테이블 (Lookup Table)

```python
GPU_ARCHITECTURE_SPEC_TABLE: Dict[float, GpuArchitectureFeatures] = {
    6.1: GpuArchitectureFeatures(
        architecture_name="Pascal",
        compute_capability=6.1,
        has_tensor_cores=False,
        supports_fp16_native=False,
        supports_bf16_native=False,
        supports_fp8_native=False,
        supports_fp4_native=False,
        supports_flash_attn=False,
        recommended_kv_type="q8_0"
    ),
    7.5: GpuArchitectureFeatures(
        architecture_name="Turing",
        compute_capability=7.5,
        has_tensor_cores=True,
        supports_fp16_native=True,
        supports_bf16_native=False,
        supports_fp8_native=False,
        supports_fp4_native=False,
        supports_flash_attn=False,
        recommended_kv_type="q8_0"
    ),
    8.6: GpuArchitectureFeatures(
        architecture_name="Ampere",
        compute_capability=8.6,
        has_tensor_cores=True,
        supports_fp16_native=True,
        supports_bf16_native=True,
        supports_fp8_native=False,
        supports_fp4_native=False,
        supports_flash_attn=True,
        recommended_kv_type="q8_0"
    ),
    8.9: GpuArchitectureFeatures(
        architecture_name="Ada Lovelace",
        compute_capability=8.9,
        has_tensor_cores=True,
        supports_fp16_native=True,
        supports_bf16_native=True,
        supports_fp8_native=True,
        supports_fp4_native=False,
        supports_flash_attn=True,
        recommended_kv_type="fp8"
    ),
    12.0: GpuArchitectureFeatures(
        architecture_name="Blackwell",
        compute_capability=12.0,
        has_tensor_cores=True,
        supports_fp16_native=True,
        supports_bf16_native=True,
        supports_fp8_native=True,
        supports_fp4_native=True,
        supports_flash_attn=True,
        recommended_kv_type="fp8"
    ),
}
```
