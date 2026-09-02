#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# 하드웨어 적응형 llama.cpp JIT 빌드기.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_DIR="${LLAMA_CPP_SOURCE_DIR:-${GATEWAY_DIR}/src/llama_cpp_src}"
BUILD_DIR="${GATEWAY_DIR}/build/llama"
BIN_DIR="${GATEWAY_DIR}/bin"
PROFILE_FILE="${GATEWAY_DIR}/config/hardware_profile.json"

log_info() { echo "[INFO] $*"; }
log_warn() { echo "[WARN] $*" >&2; }

detect_vllm_status() {
    local health_url="${VLLM_HEALTH_URL:-http://127.0.0.1:8081/health}"
    if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "${health_url}" >/dev/null 2>&1; then
        echo true
    else
        echo false
    fi
}

write_runtime_status() {
    local selected="$1"
    local vllm_ok="${2:-false}"
    local cuda_ok="${3:-false}"
    local cpu_ok="${4:-false}"
    python3 - "${PROFILE_FILE}" "${selected}" "${vllm_ok}" "${cuda_ok}" "${cpu_ok}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
profile = json.loads(path.read_text(encoding="utf-8"))
profile["runtime_backend"] = sys.argv[2]
profile["runtime_backend_status"] = {
    "vllm": sys.argv[3].lower() == "true",
    "llama.cpp-cuda": sys.argv[4].lower() == "true",
    "llama.cpp-cpu-openblas": sys.argv[5].lower() == "true",
}
path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

mkdir -p "${BIN_DIR}" "${GATEWAY_DIR}/config"

# 프로버 출력은 이 스크립트 내부에서만 생성되며 외부 입력을 eval하지 않습니다.
PROBE_JSON="$(python3 "${SCRIPT_DIR}/probe_hardware.py")"
printf '%s\n' "${PROBE_JSON}" > "${PROFILE_FILE}"
PROBE_ENV="$(python3 "${SCRIPT_DIR}/probe_hardware.py" --export-env)"
eval "${PROBE_ENV}"

log_info "CPU=${DETECTED_CPU_MODEL:-Unknown}; GPU=${DETECTED_GPU_MODEL:-None}; backend=${LLAMA_RECOMMENDED_BACKEND:-cpu}"

ensure_source() {
    if [[ -f "${SRC_DIR}/CMakeLists.txt" ]]; then
        return 0
    fi
    if [[ "${LLAMA_CPP_AUTO_CLONE:-true}" != "true" ]]; then
        return 1
    fi
    if ! command -v git >/dev/null 2>&1; then
        log_warn "llama.cpp 소스와 git이 없어 wheel/기존 런타임 fallback으로 전환합니다."
        return 1
    fi
    local repository="${LLAMA_CPP_REPOSITORY:-https://github.com/ggml-org/llama.cpp.git}"
    local ref="${LLAMA_CPP_REF:-master}"
    log_info "llama.cpp 소스를 가져옵니다: ${repository} (${ref})"
    if [[ -e "${SRC_DIR}" ]]; then
        log_warn "기존 llama.cpp 경로가 CMake 소스가 아니므로 자동 clone을 건너뜁니다: ${SRC_DIR}"
        return 1
    fi
    git clone --depth 1 --branch "${ref}" "${repository}" "${SRC_DIR}"
}

ensure_toolchain() {
    if command -v cmake >/dev/null 2>&1 && command -v c++ >/dev/null 2>&1; then
        return 0
    fi
    log_warn "CMake/C++ toolchain이 없어 설치를 시도합니다."
    if [[ "${EUID}" -eq 0 ]]; then
        apt-get update -qq && apt-get install -y build-essential cmake
    else
        sudo apt-get update -qq && sudo apt-get install -y build-essential cmake
    fi
}

run_build() {
    local backend="$1"
    local build_dir="${BUILD_DIR}/${backend}"
    local -a cmake_args=(
        -S "${SRC_DIR}" -B "${build_dir}"
        -DCMAKE_BUILD_TYPE=Release
        -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF
        -DCMAKE_C_FLAGS="${LLAMA_COMPILER_FLAGS:--march=native}"
        -DCMAKE_CXX_FLAGS="${LLAMA_COMPILER_FLAGS:--march=native}"
    )
    if [[ "${backend}" == "cuda" ]]; then
        local cuda_arch="61"
        if [[ "${LLAMA_CMAKE_FLAGS:-}" =~ CMAKE_CUDA_ARCHITECTURES=([0-9]+) ]]; then
            cuda_arch="${BASH_REMATCH[1]}"
        fi
        cmake_args+=("-DGGML_CUDA=ON" "-DCMAKE_CUDA_ARCHITECTURES=${cuda_arch}")
    else
        cmake_args+=("-DGGML_CUDA=OFF" "-DGGML_OPENBLAS=ON")
    fi
    cmake "${cmake_args[@]}"
    cmake --build "${build_dir}" --config Release -j "$(nproc 2>/dev/null || echo 2)"
    local candidate="${build_dir}/bin/llama-server"
    [[ -f "${candidate}" ]] || candidate="${build_dir}/llama-server"
    [[ -f "${candidate}" ]] || return 1
    if ! "${candidate}" --version >/dev/null 2>&1; then
        log_warn "${backend} llama-server smoke test 실패"
        return 1
    fi
    cp "${candidate}" "${BIN_DIR}/llama-server"
    chmod +x "${BIN_DIR}/llama-server"
    return 0
}

if ! ensure_source; then
    if python3 -c 'import llama_cpp' >/dev/null 2>&1; then
        log_info "llama-cpp-python wheel이 설치되어 있어 Python runtime fallback을 사용합니다."
        write_runtime_status "llama.cpp-cpu-openblas" false false true
    else
        log_warn "사용 가능한 llama.cpp 소스/wheel이 없어 기존 vLLM 또는 CPU runtime을 유지합니다."
        write_runtime_status "vllm" "$(detect_vllm_status)" false false
    fi
    exit 0
fi

if ! ensure_toolchain; then
    log_warn "CMake/C++ toolchain을 준비하지 못해 기존 runtime fallback으로 전환합니다."
    write_runtime_status "vllm" "$(detect_vllm_status)" false false
    exit 0
fi
if [[ "${LLAMA_RECOMMENDED_BACKEND:-cpu}" == "cuda" ]]; then
    set +e
    run_build cuda
    CUDA_RESULT=$?
    set -e
    if [[ "${CUDA_RESULT}" -eq 0 ]]; then
        log_info "CUDA llama.cpp 빌드 및 smoke test 통과"
        write_runtime_status "llama.cpp-cuda" false true false
        exit 0
    fi
    log_warn "CUDA/driver 호환성 실패; CPU OpenBLAS fallback을 시도합니다."
fi

set +e
run_build cpu
CPU_RESULT=$?
set -e
if [[ "${CPU_RESULT}" -eq 0 ]]; then
    log_info "CPU OpenBLAS llama.cpp fallback 빌드 및 smoke test 통과"
    write_runtime_status "llama.cpp-cpu-openblas" false false true
    exit 0
fi

log_warn "llama.cpp JIT 빌드가 실패했지만 migration bootstrap은 vLLM/기존 Python runtime으로 계속 진행합니다."
write_runtime_status "vllm" "$(detect_vllm_status)" false false
exit 0
