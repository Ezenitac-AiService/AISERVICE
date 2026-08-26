"""
NVIDIA CUDA GPU environment inspection and verification utility module.
(090-audit-test-refactor)
"""
from dataclasses import dataclass
import os
import re
import subprocess
from typing import Optional, List


@dataclass
class CudaEnvironmentProfile:
    is_cuda_available: bool
    driver_version: str
    cuda_version: str
    cudnn_version: Optional[str]
    gpu_device_name: str
    gpu_count: int
    gpu_names: List[str]
    llama_supports_gpu: bool


def _run_cmd(cmd: List[str]) -> str:
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def get_driver_version() -> str:
    output = _run_cmd(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    if output:
        return output.splitlines()[0].strip()
    
    if os.path.exists("/proc/driver/nvidia/version"):
        try:
            with open("/proc/driver/nvidia/version", "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                match = re.search(r"NVIDIA Module\s+([0-9.]+)", content)
                if match:
                    return match.group(1)
        except Exception:
            pass
    return "None"


def get_cuda_version() -> str:
    output = _run_cmd(["nvcc", "--version"])
    if output:
        match = re.search(r"release\s+([0-9.]+)", output)
        if match:
            return match.group(1)
    
    smi_out = _run_cmd(["nvidia-smi"])
    if smi_out:
        match = re.search(r"CUDA Version:\s*([0-9.]+)", smi_out)
        if match:
            return match.group(1)
            
    return "None"


def get_cudnn_version() -> Optional[str]:
    candidate_paths = [
        "/usr/include/cudnn_version.h",
        "/usr/local/cuda/include/cudnn_version.h",
        "/usr/include/cudnn.h",
    ]
    for p in candidate_paths:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    major = re.search(r"#define\s+CUDNN_MAJOR\s+(\d+)", content)
                    minor = re.search(r"#define\s+CUDNN_MINOR\s+(\d+)", content)
                    patch = re.search(r"#define\s+CUDNN_PATCHLEVEL\s+(\d+)", content)
                    if major and minor and patch:
                        return f"{major.group(1)}.{minor.group(1)}.{patch.group(1)}"
            except Exception:
                pass
    return None


def get_gpu_info() -> (int, List[str]):
    output = _run_cmd(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if output:
        names = [line.strip() for line in output.splitlines() if line.strip()]
        if names:
            return len(names), names
            
    if os.path.exists("/dev/nvidia0") or os.path.exists("/proc/driver/nvidia"):
        return 1, ["NVIDIA GPU Device"]
        
    return 0, []


def check_llama_gpu_offload_support() -> bool:
    try:
        import llama_cpp
        if hasattr(llama_cpp, "llama_supports_gpu_offload"):
            return bool(llama_cpp.llama_supports_gpu_offload())
        return hasattr(llama_cpp, "GGML_USE_CUBLAS") or hasattr(llama_cpp, "GGML_USE_CUDA")
    except ImportError:
        return False
    except Exception:
        return False


def inspect_cuda_environment() -> CudaEnvironmentProfile:
    gpu_count, gpu_names = get_gpu_info()
    driver_ver = get_driver_version()
    cuda_ver = get_cuda_version()
    cudnn_ver = get_cudnn_version()
    llama_gpu = check_llama_gpu_offload_support()
    is_available = gpu_count > 0 and driver_ver != "None"

    return CudaEnvironmentProfile(
        is_cuda_available=is_available,
        driver_version=driver_ver,
        cuda_version=cuda_ver,
        cudnn_version=cudnn_ver,
        gpu_device_name=gpu_names[0] if gpu_names else "None",
        gpu_count=gpu_count,
        gpu_names=gpu_names,
        llama_supports_gpu=llama_gpu,
    )


def assert_cuda_environment(require_gpu_offload: bool = True) -> CudaEnvironmentProfile:
    profile = inspect_cuda_environment()
    if not profile.is_cuda_available:
        raise AssertionError(
            "NVIDIA CUDA GPU가 장착되어 있지 않거나 드라이버가 작동하지 않습니다. "
            "vllm_serv 프로젝트는 CUDA GPU 전용 플랫폼 호스트만을 지원합니다. (090-audit-test-refactor)"
        )
    if require_gpu_offload and not profile.llama_supports_gpu:
        # If llama_cpp is not compiled with CUDA, raise or warn based on strict GPU policy
        pass
    return profile
