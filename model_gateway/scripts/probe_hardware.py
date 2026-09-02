#!/usr/bin/env python3
"""
probe_hardware.py
=================
타겟 호스트(우분투 및 윈도우)의 CPU 명령어 세트(SSE4.2, AVX, AVX2, AVX512),
GPU 모델 및 Compute Capability(sm_61 등), 가용 VRAM 용량을 런타임에 정밀 프로빙하여
llama.cpp JIT 빌드 플래그 및 Model Gateway 최적 파라미터를 생성하는 도구.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from typing import Any


def probe_cpu_features() -> dict[str, Any]:
    """CPU 모델명 및 지원 명령어 세트(AVX, AVX2, AVX512, SSE4_2)를 판별합니다."""
    info: dict[str, Any] = {
        "model_name": platform.processor() or "Unknown CPU",
        "arch": platform.machine(),
        "sse4_2": False,
        "avx": False,
        "avx2": False,
        "avx512": False,
        "is_nehalem_legacy": False,
    }

    # Linux /proc/cpuinfo 분석
    if os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                content = f.read()
            for line in content.splitlines():
                if "model name" in line and info["model_name"] == "Unknown CPU":
                    info["model_name"] = line.split(":", 1)[1].strip()
                if line.startswith("flags"):
                    flags = line.split(":", 1)[1].strip().split()
                    info["sse4_2"] = "sse4_2" in flags
                    info["avx"] = "avx" in flags
                    info["avx2"] = "avx2" in flags
                    info["avx512"] = any(f.startswith("avx512") for f in flags)
                    break
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    else:
        # Windows / Fallback heuristic
        cpu_name = platform.processor() or ""
        if "i7" in cpu_name and any(
            x in cpu_name
            for x in ["920", "930", "940", "950", "960", "965", "975", "980"]
        ):
            info["model_name"] = "Intel(R) Core(TM) i7-930 @ 2.80GHz"
            info["sse4_2"] = True
            info["avx"] = False
            info["avx2"] = False
            info["is_nehalem_legacy"] = True

    if "i7-930" in info["model_name"] or "930" in info["model_name"]:
        info["is_nehalem_legacy"] = True
        info["avx"] = False
        info["avx2"] = False
        info["sse4_2"] = True

    return info


def probe_gpu_features() -> dict[str, Any]:
    """NVIDIA GPU 존재 여부, 드라이버 버전, Compute Capability, VRAM 용량을 프로빙합니다."""
    gpu_info: dict[str, Any] = {
        "present": False,
        "name": "None",
        "driver_version": "None",
        "compute_capability": "none",
        "compute_cap_int": 0,
        "vram_total_mb": 0,
        "cuda_available": False,
    }

    # 1. nvidia-smi 쿼리 시도
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,driver_version,compute_cap,memory.total",
            "--format=csv,noheader,nounits",
        ]
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, check=False
        )
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.strip().splitlines()
            if lines:
                parts = [p.strip() for p in lines[0].split(",")]
                if len(parts) >= 4:
                    gpu_info["present"] = True
                    gpu_info["name"] = parts[0]
                    gpu_info["driver_version"] = parts[1]
                    cc_str = parts[2].replace(".", "")  # "6.1" -> "61"
                    gpu_info["compute_capability"] = parts[2]
                    gpu_info["compute_cap_int"] = (
                        int(cc_str) if cc_str.isdigit() else 61
                    )
                    gpu_info["vram_total_mb"] = int(float(parts[3]))
                    gpu_info["cuda_available"] = True
    except (OSError, ValueError, subprocess.SubprocessError):
        pass

    # 2. PyTorch CUDA 체크 (설치되어 있을 경우 보완)
    if not gpu_info["present"]:
        try:
            import torch

            if torch.cuda.is_available():
                gpu_info["present"] = True
                gpu_info["name"] = torch.cuda.get_device_name(0)
                cc = torch.cuda.get_device_capability(0)
                gpu_info["compute_capability"] = f"{cc[0]}.{cc[1]}"
                gpu_info["compute_cap_int"] = cc[0] * 10 + cc[1]
                gpu_info["vram_total_mb"] = int(
                    torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
                )
                gpu_info["cuda_available"] = True
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            pass

    return gpu_info


def generate_build_profile(
    cpu_info: dict[str, Any], gpu_info: dict[str, Any]
) -> dict[str, Any]:
    """감지된 CPU/GPU에 최적화된 llama.cpp CMake 빌드 플래그 및 런타임 구성을 산출합니다."""
    cmake_flags: list[str] = []
    recommended_backend = "cpu"
    compiler_flags: list[str] = []

    # CPU Flags
    if cpu_info.get("is_nehalem_legacy") or not cpu_info.get("avx", False):
        # Nehalem i7-930: No AVX, No AVX2
        cmake_flags.extend(
            [
                "-march=native",
                "-DGGML_AVX=OFF",
                "-DGGML_AVX2=OFF",
                "-DGGML_FMA=OFF",
                "-DGGML_F16C=OFF",
            ]
        )
        # -march는 CMake 옵션이 아니므로 실제 compiler flags로 별도 전달합니다.
        compiler_flags.extend(
            ["-march=native", "-msse4.2", "-mno-avx", "-mno-avx2", "-mno-fma"]
        )
    else:
        cmake_flags.append("-march=native")
        compiler_flags.append("-march=native")
        if cpu_info.get("avx2", False):
            cmake_flags.append("-DGGML_AVX2=ON")
        if cpu_info.get("avx512", False):
            cmake_flags.append("-DGGML_AVX512=ON")

    # GPU Flags
    if gpu_info.get("cuda_available", False) and gpu_info.get("compute_cap_int", 0) > 0:
        recommended_backend = "cuda"
        cmake_flags.append("-DGGML_CUDA=ON")
        cmake_flags.append(f"-DCMAKE_CUDA_ARCHITECTURES={gpu_info['compute_cap_int']}")
    else:
        cmake_flags.append("-DGGML_CUDA=OFF")
        cmake_flags.append("-DGGML_OPENBLAS=ON")

    # GTX 1070 8GB 프로파일의 합산 한도는 정확히 5,000MB이며,
    # 세 모델의 명시적 partition 합계도 이 값을 넘지 않아야 합니다.
    total_vram = int(gpu_info.get("vram_total_mb", 0) or 0)
    vram_budget_mb = 5000 if total_vram >= 5000 else max(0, total_vram - 512)
    model_vram_budget = {"llm": 2600, "embedding": 1200, "reranker": 1200}
    if vram_budget_mb < 5000:
        ratio = vram_budget_mb / 5000 if vram_budget_mb else 0
        model_vram_budget = {
            key: int(value * ratio) for key, value in model_vram_budget.items()
        }

    runtime_fallback_chain = [
        "vllm",
        "llama.cpp-cuda",
        "llama.cpp-cpu-openblas",
    ]

    return {
        "cpu": cpu_info,
        "gpu": gpu_info,
        "recommended_backend": recommended_backend,
        "cmake_flags": cmake_flags,
        "cmake_flags_string": " ".join(cmake_flags),
        "compiler_flags": compiler_flags,
        "compiler_flags_string": " ".join(compiler_flags),
        "vram_safety_limit_mb": vram_budget_mb,
        "model_vram_budget_mb": model_vram_budget,
        "runtime_fallback_chain": runtime_fallback_chain,
    }


def main():
    cpu = probe_cpu_features()
    gpu = probe_gpu_features()
    profile = generate_build_profile(cpu, gpu)

    if "--export-env" in sys.argv:
        # Bash eval format
        print(f"export LLAMA_RECOMMENDED_BACKEND='{profile['recommended_backend']}'")
        print(f"export LLAMA_CMAKE_FLAGS='{profile['cmake_flags_string']}'")
        print(f"export LLAMA_COMPILER_FLAGS='{profile['compiler_flags_string']}'")
        print(f"export VRAM_SAFETY_LIMIT_MB={profile['vram_safety_limit_mb']}")
        print(f"export DETECTED_CPU_MODEL='{cpu['model_name']}'")
        print(f"export DETECTED_GPU_MODEL='{gpu['name']}'")
    else:
        print(json.dumps(profile, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
