"""
GPU, CPU, and CUDA Acceleration Detector and 3-Axis Decoupled Hardware Evaluation Engine.
Provides hardware validation, VRAM memory checks, CPU instruction detection,
and immutable 6-tier architecture capability matrices (Pascal to Blackwell).
"""

import os
import re
import subprocess
import shutil
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class GpuValidationError(Exception):
    """Base exception for GPU validation errors."""
    pass


class GpuAccelerationError(GpuValidationError):
    """Raised when GPU is not detected, CUDA backend is unavailable, or CPU-only binary is executed."""
    pass


class VramOverflowError(GpuValidationError):
    """Raised when VRAM is insufficient or model layers fail to 100% offload to GPU VRAM."""
    pass


class PortCollisionError(GpuValidationError):
    """Raised when port 8081 is occupied by zombie or colliding process."""
    pass


class GpuArchitectureEnum(str, Enum):
    """GPU Architecture Classification Enum."""
    PASCAL_SM61 = "pascal_sm61"          # SM 6.1 (GTX 1070 8GB, GTX 1080 Ti 11GB 등)
    TURING_SM75 = "turing_sm75"          # SM 7.5 (RTX 2060, RTX 2080 8GB 등)
    AMPERE_SM86 = "ampere_sm86"          # SM 8.6 (RTX 3060 12GB, RTX 3070 8GB, RTX 3080 등)
    ADA_SM89 = "ada_sm89"                # SM 8.9 (RTX 4060 8GB, RTX 4070 12GB, RTX 4080 16GB 등)
    BLACKWELL_SM120 = "blackwell_sm120"  # SM 12.0 (RTX 5060 8GB, RTX 5060 Ti 16GB, RTX 5080 16/24GB 등)
    UNKNOWN = "unknown"


class HardwareTierEnum(str, Enum):
    """VRAM 기반 하드웨어 플랫폼 티어 분류 (실측 벤치마크 기준)."""
    BASELINE_8GB = "BASELINE_8GB"          # GTX 1070 8GB (VRAM < 11GB): 2B 상시, 4B 온디맨드
    MID_12GB_16GB = "MID_12GB_16GB"        # RTX 3060 12GB, RTX 4070 16GB (11GB <= VRAM < 20GB): 4B/9B 상시
    HIGH_20GB_40GB = "HIGH_20GB_40GB"      # RTX 3090/4090 24GB (20GB <= VRAM < 40GB): 9B/12B 상시
    ULTRA_40GB_PLUS = "ULTRA_40GB_PLUS"    # A100 40/80GB, H100 (VRAM >= 40GB): 27B/35B 상시


class CpuArchitectureFeatures(BaseModel):
    """[Axis 3] Independent CPU Instruction Set Features."""
    cpu_model_name: str = Field(default="Generic x86_64 CPU", description="CPU model name")
    has_avx: bool = Field(default=False, description="Whether AVX is supported")
    has_avx2: bool = Field(default=False, description="Whether AVX2 is supported")
    has_fma: bool = Field(default=False, description="Whether FMA3 is supported")
    requires_gpu_only: bool = Field(default=False, description="Enforce 100% GPU offload (-ngl 999) due to missing AVX")


class GpuArchitectureFeatures(BaseModel):
    """[Axis 1] Independent GPU Architecture Generation Specs (Decoupled from VRAM capacity)."""
    architecture_name: str = Field(..., description="Architecture name (Pascal, Turing, Ampere, Ada, Blackwell)")
    compute_capability: float = Field(..., description="CUDA Compute Capability (6.1, 7.5, 8.6, 8.9, 12.0)")
    has_tensor_cores: bool = Field(..., description="Whether Tensor Cores are present")
    supports_fp16_native: bool = Field(..., description="Native 1:1 FP16 fast compute support")
    supports_bf16_native: bool = Field(..., description="BF16 compute support")
    supports_fp8_native: bool = Field(..., description="FP8 (Transformer Engine) support")
    supports_fp4_native: bool = Field(default=False, description="FP4 (Blackwell NVFP4) support")
    supports_flash_attn: bool = Field(..., description="FlashAttention-3/4 support (SM >= 8.0)")
    recommended_kv_type: str = Field(default="q8_0", description="Recommended KV Cache quantization (q8_0, fp16, fp8, fp4)")


class DynamicHardwareProfile(BaseModel):
    """[Axis 1 + Axis 2 + Axis 3] 3-Axis Decoupled Real-Time Hardware Synthesis Profile."""
    device_name: str = Field(default="NVIDIA GPU", description="GPU device model name")
    compute_capability: float = Field(default=6.1, description="CUDA Compute Capability")
    gpu_features: GpuArchitectureFeatures = Field(..., description="GPU architecture generation specs")
    cpu_features: CpuArchitectureFeatures = Field(..., description="CPU instruction specs")
    total_vram_mb: int = Field(default=8192, description="Total physical VRAM in MB")
    free_vram_mb: int = Field(default=6500, description="Available physical VRAM in MB")
    hardware_tier: HardwareTierEnum = Field(default=HardwareTierEnum.BASELINE_8GB, description="하드웨어 플랫폼 티어")
    recommended_model: str = Field(default="qwen3.5-2b", description="Recommended serving model based on VRAM and KV type")
    recommended_batch_model: str = Field(default="qwen3.5-4b", description="Recommended batch/deep-analysis model")
    dynamic_n_ctx: int = Field(default=65536, description="Dynamically calculated max safe context window")
    resident_standard_n_ctx: int = Field(default=65536, description="상시 모델 표준 컨텍스트")
    resident_ultra_n_ctx: int = Field(default=131072, description="상시 모델 울트라 컨텍스트")
    batch_n_ctx: int = Field(default=32768, description="배치 모델 표준 컨텍스트")
    min_target_tps: float = Field(default=30.0, description="보장 최소 TPS SLA")
    use_q8_kv: bool = Field(default=True, description="Whether Q8_0 KV Cache is active")
    use_fp8_kv: bool = Field(default=False, description="Whether FP8 KV Cache is active")
    use_fp4_kv: bool = Field(default=False, description="Whether FP4 KV Cache is active")
    use_flash_attn: bool = Field(default=False, description="Whether FlashAttention is active")
    force_all_gpu_layers: bool = Field(default=True, description="Enforce 100% GPU offload (-ngl 999)")


class GpuDeviceInfo(BaseModel):
    """GPU Device and CUDA Runtime Information."""
    device_id: int = Field(default=0, description="GPU device index")
    name: str = Field(default="NVIDIA GPU", description="GPU device model name")
    total_vram_mb: int = Field(default=0, description="Total VRAM capacity in MB")
    free_vram_mb: int = Field(default=0, description="Currently available VRAM in MB")
    driver_version: Optional[str] = Field(default=None, description="NVIDIA Driver version")
    cuda_version: Optional[str] = Field(default=None, description="CUDA Runtime version")
    is_cuda_available: bool = Field(default=False, description="Whether CUDA GPU acceleration is available")


class VramOffloadStatus(BaseModel):
    """VRAM Offload Verification Status."""
    model_id: str = Field(..., description="Model identifier")
    total_layers: int = Field(default=0, description="Total transformer layers")
    offloaded_layers: int = Field(default=0, description="Layers offloaded to GPU VRAM")
    is_fully_offloaded: bool = Field(default=False, description="True if 100% of layers offloaded to VRAM")
    offloaded_vram_mb: int = Field(default=0, description="VRAM footprint in MB")
    has_clip_offload: Optional[bool] = Field(default=None, description="Multimodal CLIP projector offloaded")


# Immutable 6-Tier GPU Architecture Specs Lookup Table
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
        recommended_kv_type="fp4"
    ),
}


def detect_cpu_capabilities() -> CpuArchitectureFeatures:
    """[Axis 3] Real-time detection of host CPU instruction set (AVX/AVX2/FMA)."""
    cpu_name = "Generic x86_64 CPU"
    has_avx = False
    has_avx2 = False
    has_fma = False

    try:
        # Check Linux /proc/cpuinfo
        if os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                model_match = re.search(r"model name\s*:\s*(.+)", content)
                if model_match:
                    cpu_name = model_match.group(1).strip()
                flags_match = re.search(r"flags\s*:\s*(.+)", content)
                if flags_match:
                    flags = flags_match.group(1).split()
                    has_avx = "avx" in flags
                    has_avx2 = "avx2" in flags
                    has_fma = "fma" in flags
        elif os.name == "nt":
            # Windows fallback
            cpu_name = os.environ.get("PROCESSOR_IDENTIFIER", "Windows x64 CPU")
            # In Windows Python, default conservative check
            has_avx = True
            has_avx2 = True
    except Exception:
        pass

    requires_gpu_only = not has_avx2
    return CpuArchitectureFeatures(
        cpu_model_name=cpu_name,
        has_avx=has_avx,
        has_avx2=has_avx2,
        has_fma=has_fma,
        requires_gpu_only=requires_gpu_only
    )


def detect_gpu_architecture(compute_cap: float) -> GpuArchitectureFeatures:
    """[Axis 1] Maps compute capability to immutable GPU architecture specs."""
    # Find closest known architecture
    if compute_cap in GPU_ARCHITECTURE_SPEC_TABLE:
        return GPU_ARCHITECTURE_SPEC_TABLE[compute_cap]
    
    # Range fallback
    if compute_cap < 7.0:
        return GPU_ARCHITECTURE_SPEC_TABLE[6.1]
    elif compute_cap < 8.0:
        return GPU_ARCHITECTURE_SPEC_TABLE[7.5]
    elif compute_cap < 8.8:
        return GPU_ARCHITECTURE_SPEC_TABLE[8.6]
    elif compute_cap < 10.0:
        return GPU_ARCHITECTURE_SPEC_TABLE[8.9]
    else:
        return GPU_ARCHITECTURE_SPEC_TABLE[12.0]


def calculate_3axis_dynamic_context(
    total_vram_mb: int,
    kv_cache_type: str = "q8_0",
    model_name: str = "qwen3.5-2b"
) -> int:
    """[Axis 2] Calculates dynamic context window from VRAM budget and KV byte efficiency."""
    # Base reservation: OS (3700MB) + BGE (1412MB) + Safety Margin (600MB)
    v_reserved = 3700 + 1412 + 600
    
    # Model weight footprint
    if "2b" in model_name.lower():
        w_model = 1500
    elif "4b" in model_name.lower():
        w_model = 2800
    elif "9b" in model_name.lower():
        w_model = 5600
    else:
        w_model = 1500

    v_kv_budget = max(400, total_vram_mb - v_reserved - w_model)

    # Bytes per token for GQA (Qwen 3.5 28 layers, 4 KV heads, 128 dim)
    # total_bytes = 2 * 28 * 4 * 128 * bytes_per_elem = 28,672 * bytes_per_elem
    if kv_cache_type == "fp4":
        bytes_per_elem = 0.5
    elif kv_cache_type in ("q8_0", "fp8"):
        bytes_per_elem = 1.0
    else:
        bytes_per_elem = 2.0  # fp16

    bytes_per_token = 28672 * bytes_per_elem
    raw_tokens = int((v_kv_budget * 1024 * 1024) / bytes_per_token)

    # Align to power of 2 steps (16K, 32K, 48K, 64K, 128K)
    if raw_tokens >= 131072:
        return 131072
    elif raw_tokens >= 65536:
        return 65536
    elif raw_tokens >= 49152:
        return 49152
    elif raw_tokens >= 32768:
        return 32768
    elif raw_tokens >= 16384:
        return 16384
    else:
        return max(8192, (raw_tokens // 2048) * 2048)


def detect_hardware_capabilities(
    device_index: int = 0,
    forced_compute_cap: Optional[float] = None,
    forced_vram_mb: Optional[int] = None
) -> DynamicHardwareProfile:
    """[Axis 1 + 2 + 3] Real-time hardware synthesis profile evaluator."""
    cpu_feat = detect_cpu_capabilities()
    
    # Query GPU
    device_name = "NVIDIA GPU"
    compute_cap = 6.1
    total_vram = 8192
    free_vram = 6500

    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        device_name = name
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_vram = int(info.total / (1024 * 1024))
        free_vram = int(info.free / (1024 * 1024))

        # Query compute capability via PyNVML / CUDA Driver if available
        try:
            major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
            compute_cap = float(f"{major}.{minor}")
        except Exception:
            if "1070" in device_name or "1080" in device_name:
                compute_cap = 6.1
            elif "2080" in device_name or "2060" in device_name:
                compute_cap = 7.5
            elif "3060" in device_name or "3070" in device_name or "3080" in device_name:
                compute_cap = 8.6
            elif "4060" in device_name or "4070" in device_name or "4080" in device_name or "4090" in device_name:
                compute_cap = 8.9
            elif "5060" in device_name or "5070" in device_name or "5080" in device_name or "5090" in device_name:
                compute_cap = 12.0
            else:
                compute_cap = 6.1
        pynvml.nvmlShutdown()
    except Exception:
        # Fallback to defaults
        pass

    # Apply mock/forced parameters for testing
    if forced_compute_cap is not None:
        compute_cap = forced_compute_cap
    if forced_vram_mb is not None:
        total_vram = forced_vram_mb
        free_vram = int(forced_vram_mb * 0.8)

    gpu_feat = detect_gpu_architecture(compute_cap)
    
    # ──────────────────────────────────────────────────────────────────────
    # 4-Tier VRAM-Based Hardware Platform Scaling (실측 벤치마크 기반)
    # ──────────────────────────────────────────────────────────────────────
    if total_vram >= 40000:  # A100 40GB/80GB, H100
        hw_tier = HardwareTierEnum.ULTRA_40GB_PLUS
        recommended_model = "qwen3.6-27b"
        recommended_batch = "qwen3.6-35b-a3b"
        resident_std = 131072
        resident_ultra = 131072
        batch_ctx = 131072
        min_tps = 30.0
    elif total_vram >= 20000:  # RTX 3090/4090 24GB
        hw_tier = HardwareTierEnum.HIGH_20GB_40GB
        recommended_model = "qwen3.5-9b"
        recommended_batch = "gemma4-12b"
        resident_std = 65536
        resident_ultra = 131072
        batch_ctx = 32768
        min_tps = 35.0
    elif total_vram >= 11000:  # RTX 3060 12GB, RTX 4070 16GB
        hw_tier = HardwareTierEnum.MID_12GB_16GB
        recommended_model = "qwen3.5-4b"
        recommended_batch = "qwen3.5-9b"
        resident_std = 32768
        resident_ultra = 65536
        batch_ctx = 32768
        min_tps = 40.0
    else:  # GTX 1070 8GB (최소 기준 플랫폼)
        hw_tier = HardwareTierEnum.BASELINE_8GB
        recommended_model = "qwen3.5-2b"
        recommended_batch = "qwen3.5-4b"
        resident_std = 16384
        resident_ultra = 32768
        batch_ctx = 16384
        min_tps = 50.0

    dynamic_ctx = calculate_3axis_dynamic_context(
        total_vram_mb=total_vram,
        kv_cache_type=gpu_feat.recommended_kv_type,
        model_name=recommended_model
    )

    use_q8 = gpu_feat.recommended_kv_type == "q8_0"
    use_fp8 = gpu_feat.recommended_kv_type == "fp8"
    use_fp4 = gpu_feat.recommended_kv_type == "fp4"
    use_flash_attn = gpu_feat.supports_flash_attn
    force_all_gpu = cpu_feat.requires_gpu_only

    return DynamicHardwareProfile(
        device_name=device_name,
        compute_capability=compute_cap,
        gpu_features=gpu_feat,
        cpu_features=cpu_feat,
        total_vram_mb=total_vram,
        free_vram_mb=free_vram,
        hardware_tier=hw_tier,
        recommended_model=recommended_model,
        recommended_batch_model=recommended_batch,
        dynamic_n_ctx=dynamic_ctx,
        resident_standard_n_ctx=resident_std,
        resident_ultra_n_ctx=resident_ultra,
        batch_n_ctx=batch_ctx,
        min_target_tps=min_tps,
        use_q8_kv=use_q8,
        use_fp8_kv=use_fp8,
        use_fp4_kv=use_fp4,
        use_flash_attn=use_flash_attn,
        force_all_gpu_layers=force_all_gpu
    )


def check_gpu_availability() -> GpuDeviceInfo:
    """Scans system for NVIDIA GPU and verifies CUDA hardware acceleration backend."""
    nvidia_smi_path = shutil.which("nvidia-smi")
    if not nvidia_smi_path:
        raise GpuAccelerationError(
            "NVIDIA GPU driver / nvidia-smi tool not found. GPU acceleration is required."
        )

    try:
        cmd = [
            nvidia_smi_path,
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = res.stdout.strip().split("\n")
        if not lines or not lines[0]:
            raise GpuAccelerationError("No active NVIDIA GPU detected by nvidia-smi.")

        parts = [p.strip() for p in lines[0].split(",")]
        gpu_name = parts[0] if len(parts) > 0 else "NVIDIA GPU"
        total_vram = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 11264
        free_vram = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 8500
        driver_ver = parts[3] if len(parts) > 3 else "Unknown"

        detected_cuda_version: Optional[str] = None
        try:
            smi_res = subprocess.run(
                [nvidia_smi_path], capture_output=True, text=True, check=True
            )
            cuda_match = re.search(r'CUDA Version:\s*([\d.]+)', smi_res.stdout)
            if cuda_match:
                detected_cuda_version = cuda_match.group(1)
        except (subprocess.CalledProcessError, OSError):
            pass

        return GpuDeviceInfo(
            device_id=0,
            name=gpu_name,
            total_vram_mb=total_vram,
            free_vram_mb=free_vram,
            driver_version=driver_ver,
            cuda_version=detected_cuda_version,
            is_cuda_available=True
        )

    except subprocess.CalledProcessError as e:
        raise GpuAccelerationError(f"nvidia-smi command failed: {e}")
    except Exception as e:
        if isinstance(e, GpuAccelerationError):
            raise e
        raise GpuAccelerationError(f"Failed to verify GPU hardware: {str(e)}")


def get_nvml_vram_info(device_index: int = 0) -> GpuDeviceInfo:
    """Non-blocking VRAM inspection via PyNVML C-API (<1ms), with nvidia-smi fallback."""
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        total_mb = int(info.total / (1024 * 1024))
        free_mb = int(info.free / (1024 * 1024))
        pynvml.nvmlShutdown()
        return GpuDeviceInfo(
            device_id=device_index,
            name=name,
            total_vram_mb=total_mb,
            free_vram_mb=free_mb,
            is_cuda_available=True
        )
    except Exception:
        try:
            return check_gpu_availability()
        except Exception:
            return GpuDeviceInfo(
                device_id=device_index,
                name="NVIDIA GPU (WSL2 Auto Detect)",
                total_vram_mb=8192,
                free_vram_mb=6500,
                is_cuda_available=True
            )


def get_realtime_usable_vram(safety_margin_mb: Optional[int] = None, n_ctx: int = 16384) -> int:
    """Returns real-time usable VRAM in MB calculated from NVML free VRAM minus dynamic safety margin."""
    try:
        if safety_margin_mb is None:
            safety_margin_mb = 500 + int(n_ctx * 0.05)
        gpu_info = get_nvml_vram_info()
        return max(0, gpu_info.free_vram_mb - safety_margin_mb)
    except Exception:
        return 0


def wait_for_nvml_vram_settled(
    poll_interval: float = 0.2,
    max_attempts: int = 5,
    delta_threshold_mb: int = 10
) -> GpuDeviceInfo:
    """Polls NVML Free VRAM until consecutive reads differ by < delta_threshold_mb."""
    import time
    prev_info = get_nvml_vram_info()
    for _ in range(max_attempts - 1):
        time.sleep(poll_interval)
        curr_info = get_nvml_vram_info()
        if abs(curr_info.free_vram_mb - prev_info.free_vram_mb) < delta_threshold_mb:
            return curr_info
        prev_info = curr_info
    return prev_info


def read_gguf_metadata_architecture(gguf_file_path: str) -> dict:
    """Fast pure-Python GGUF binary header parser extracting architecture metadata."""
    if not gguf_file_path or not os.path.exists(gguf_file_path):
        return {}

    try:
        import struct
        meta = {}
        with open(gguf_file_path, "rb") as f:
            magic = f.read(4)
            if magic != b"GGUF":
                return {}
            version, n_tensors, n_kv = struct.unpack("<IQQ", f.read(20))

            def _read_str(file_handle):
                length = struct.unpack("<Q", file_handle.read(8))[0]
                return file_handle.read(length).decode("utf-8", errors="ignore")

            def _skip_val(file_handle, v_type):
                if v_type in (0, 1, 7):
                    file_handle.read(1)
                elif v_type in (2, 3):
                    file_handle.read(2)
                elif v_type in (4, 5, 6):
                    file_handle.read(4)
                elif v_type in (10, 11, 12):
                    file_handle.read(8)
                elif v_type == 8:
                    _read_str(file_handle)
                elif v_type == 9:
                    elem_type, elem_count = struct.unpack("<IQ", file_handle.read(12))
                    for _ in range(elem_count):
                        _skip_val(file_handle, elem_type)

            for _ in range(n_kv):
                k = _read_str(f)
                val_type = struct.unpack("<I", f.read(4))[0]
                k_lower = k.lower()
                if any(x in k_lower for x in ("block_count", "head_count", "key_length", "context_length")):
                    if val_type in (4, 5):
                        val = struct.unpack("<I", f.read(4))[0]
                        if "block_count" in k_lower:
                            meta["n_layers"] = val
                        elif "head_count_kv" in k_lower:
                            meta["n_head_kv"] = val
                        elif "head_count" in k_lower:
                            meta["n_heads"] = val
                        elif "key_length" in k_lower and "key_length_swa" not in k_lower:
                            meta["head_dim"] = val
                        elif "context_length" in k_lower:
                            meta["max_rope_n_ctx"] = val
                    elif val_type in (10, 11):
                        val = struct.unpack("<Q", f.read(8))[0]
                        if "block_count" in k_lower:
                            meta["n_layers"] = val
                        elif "head_count_kv" in k_lower:
                            meta["n_head_kv"] = val
                        elif "head_count" in k_lower:
                            meta["n_heads"] = val
                        elif "key_length" in k_lower and "key_length_swa" not in k_lower:
                            meta["head_dim"] = val
                        elif "context_length" in k_lower:
                            meta["max_rope_n_ctx"] = val
                    else:
                        _skip_val(f, val_type)
                else:
                    _skip_val(f, val_type)
        return meta
    except Exception as e:
        print(f"[GpuDetector] Warning: Failed to read GGUF binary header {gguf_file_path}: {e}")
        return {}


def calculate_dynamic_log_step_size(high: int) -> int:
    """Log-scaled dynamic step size calculation."""
    import math
    if high <= 32768:
        return 512
    raw = 2 ** math.floor(math.log2(high / 64.0))
    return max(512, int(raw))


def estimate_kv_cache_vram(
    n_layers: int = 36,
    n_heads: int = 32,
    head_dim: int = 128,
    n_ctx: int = 4096,
    bytes_per_element: Optional[float] = None,
    n_head_kv: Optional[int] = None,
    kv_quant: Optional[str] = "q8_0"
) -> int:
    """Pre-flight GQA KV Cache VRAM estimator supporting Q8_0/Q4_0/FP8/FP16 quantization."""
    if bytes_per_element is None:
        if kv_quant == "fp4":
            bytes_per_element = 0.5
        elif kv_quant in ("q8_0", "q8", "fp8"):
            bytes_per_element = 1.0
        else:
            bytes_per_element = 2.0  # f16 default

    kv_heads = n_head_kv if n_head_kv is not None and n_head_kv > 0 else n_heads
    total_bytes = 2 * n_layers * kv_heads * head_dim * n_ctx * bytes_per_element
    return max(1, int(total_bytes / (1024 * 1024)))


def calculate_max_allocatable_n_ctx(
    usable_kv_budget_mb: int,
    n_layers: int = 36,
    n_heads: int = 32,
    head_dim: int = 128,
    bytes_per_element: Optional[float] = None,
    step: int = 512,
    max_cap: int = 131072,
    n_head_kv: Optional[int] = None,
    kv_quant: Optional[str] = "q8_0"
) -> int:
    """Calculates max allocatable n_ctx with GQA n_head_kv and KV quantization support."""
    if usable_kv_budget_mb <= 0:
        return 2048

    if bytes_per_element is None:
        if kv_quant == "fp4":
            bytes_per_element = 0.5
        elif kv_quant in ("q8_0", "q8", "fp8"):
            bytes_per_element = 1.0
        else:
            bytes_per_element = 2.0

    kv_heads = n_head_kv if n_head_kv is not None and n_head_kv > 0 else n_heads
    bytes_per_ctx_token = 2 * n_layers * kv_heads * head_dim * bytes_per_element
    max_bytes = usable_kv_budget_mb * 1024 * 1024
    raw_n_ctx = int(max_bytes / bytes_per_ctx_token) if bytes_per_ctx_token > 0 else 2048

    aligned_n_ctx = (raw_n_ctx // step) * step
    aligned_n_ctx = min(max_cap, max(2048, aligned_n_ctx))
    return aligned_n_ctx


def validate_cuda_build_environment() -> bool:
    """Validates that nvcc and nvidia-smi are present, blocking CPU-only fallback."""
    nvidia_smi_path = shutil.which("nvidia-smi")
    if not nvidia_smi_path:
        raise GpuAccelerationError(
            "NVIDIA GPU 드라이버(nvidia-smi)가 감지되지 않았습니다."
        )

    nvcc_path = shutil.which("nvcc")
    if not nvcc_path:
        raise GpuAccelerationError(
            "NVIDIA CUDA Toolkit (nvcc)가 감지되지 않았습니다."
        )

    try:
        import llama_cpp
        gpu_check_fn = getattr(llama_cpp, 'llama_supports_gpu_offload', None) or getattr(llama_cpp, 'llama_supports_gpu', None)
        if gpu_check_fn is not None and not gpu_check_fn():
            raise GpuAccelerationError("llama-cpp-python이 CPU 전용 모드로 설치되어 있습니다.")
    except ImportError:
        pass

    return True
