"""
Unit tests for src/core/cpu_detector.py
Validates legacy CPU detection (AVX disabled), modern CPU detection, GPU compute capability extraction, and CMake flag generation.
"""

import os
import tempfile
import pytest

from src.core.cpu_detector import (
    detect_cpu_features,
    get_llama_build_flags,
    CpuFeatureInfo,
    LlamaCppBuildFlags
)
from src.core.gpu_detector import GpuAccelerationError


LEGACY_I7_930_CPUINFO = """
processor	: 0
vendor_id	: GenuineIntel
cpu family	: 6
model		: 26
model name	: Intel(R) Core(TM) i7 CPU         930  @ 2.80GHz
stepping	: 5
microcode	: 0x1d
cpu MHz		: 2800.000
cache size	: 8192 KB
physical id	: 0
siblings	: 8
core id		: 0
cpu cores	: 4
apicid		: 0
initial apicid	: 0
fpu		: yes
fpu_exception	: yes
cpuid level	: 11
wp		: yes
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx rdtscp lm constant_tsc arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni dtes64 monitor ds_cpl vmx est tm2 ssse3 cx16 xtpr pdcm sse4_1 sse4_2 popcnt lahf_lm pti ssbd ibpb stibp tpr_shadow vnmi flexpriority ept vpid alloc_size
bugs		: cpu_meltdown spectre_v1 spectre_v2 spec_store_bypass l1tf mds swapgs itlb_multihit
bogomips	: 5600.00
clflush size	: 64
cache_alignment	: 64
address sizes	: 36 bits physical, 48 bits virtual
power management:
"""

MODERN_AVX2_CPUINFO = """
processor	: 0
vendor_id	: GenuineIntel
cpu family	: 6
model		: 158
model name	: Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz
stepping	: 5
microcode	: 0xe2
cpu MHz		: 3800.000
cache size	: 16384 KB
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand hypervisor lahf_lm abm 3dnowprefetch cpuid_fault epb invpcid_single ssbd ibrs ibpb stibp ibrs_enhanced tpr_shadow vnmi flexpriority ept vpid ept_ad fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid mpx rdseed adx smap clflushopt intel_pt xsaveopt xsavec xgetbv1 xsaves dtherm ida arat pln pts hwp hwp_notify hwp_act_window hwp_epp md_clear flush_l1d arch_capabilities
"""


def test_legacy_i7_930_cpu_detection():
    """T006 [US1]: Verifies i7 930 (Nehalem) parsing disables AVX, AVX2, F16C, FMA while keeping SSE4.2."""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write(LEGACY_I7_930_CPUINFO)
        temp_path = tf.name

    try:
        cpu_info = detect_cpu_features(cpuinfo_path=temp_path)
        assert cpu_info.model_name == "Intel(R) Core(TM) i7 CPU         930  @ 2.80GHz"
        assert cpu_info.supports_sse4_2 is True
        assert cpu_info.supports_avx is False
        assert cpu_info.supports_avx2 is False
        assert cpu_info.supports_f16c is False
        assert cpu_info.supports_fma is False
        assert cpu_info.is_fallback is False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_modern_cpu_detection():
    """T011 [US2]: Verifies modern CPU parsing enables AVX, AVX2, F16C, FMA."""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write(MODERN_AVX2_CPUINFO)
        temp_path = tf.name

    try:
        cpu_info = detect_cpu_features(cpuinfo_path=temp_path)
        assert "i7-10700K" in cpu_info.model_name
        assert cpu_info.supports_sse4_2 is True
        assert cpu_info.supports_avx is True
        assert cpu_info.supports_avx2 is True
        assert cpu_info.supports_f16c is True
        assert cpu_info.supports_fma is True
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_missing_cpuinfo_fallback():
    """T004: Verifies safe fallback mode when /proc/cpuinfo does not exist."""
    cpu_info = detect_cpu_features(cpuinfo_path="/non_existent_path_test_proc_cpuinfo")
    assert cpu_info.is_fallback is True
    assert cpu_info.supports_avx is False
    assert cpu_info.supports_avx2 is False
    assert cpu_info.supports_f16c is False
    assert cpu_info.supports_fma is False


def test_build_flags_generation_legacy(monkeypatch):
    """T006 & T007 [US1]: Verifies CMake build flags string for legacy CPU + GTX 1070 (sm_61)."""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write(LEGACY_I7_930_CPUINFO)
        temp_path = tf.name

    from src.core.cpu_detector import GpuCapabilityInfo
    monkeypatch.setattr(
        "src.core.cpu_detector.detect_gpu_capability",
        lambda: GpuCapabilityInfo(
            gpu_name="NVIDIA GeForce GTX 1070",
            compute_capability="6.1",
            cuda_arch_code="61",
            total_vram_mb=8192
        )
    )

    try:
        flags = get_llama_build_flags(cpuinfo_path=temp_path)
        assert "-DGGML_CUDA=ON" in flags.cmake_args_list
        assert "-DGGML_AVX=OFF" in flags.cmake_args_list
        assert "-DGGML_AVX2=OFF" in flags.cmake_args_list
        assert "-DGGML_F16C=OFF" in flags.cmake_args_list
        assert "-DGGML_FMA=OFF" in flags.cmake_args_list
        assert "-DCMAKE_CUDA_ARCHITECTURES=61" in flags.cmake_args_list
        assert "-DGGML_F16C=OFF -DGGML_FMA=OFF" in flags.cmake_args_str
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_build_flags_generation_modern(monkeypatch):
    """T011 [US2]: Verifies CMake build flags string for modern CPU + RTX 3060 (sm_86)."""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
        tf.write(MODERN_AVX2_CPUINFO)
        temp_path = tf.name

    from src.core.cpu_detector import GpuCapabilityInfo
    monkeypatch.setattr(
        "src.core.cpu_detector.detect_gpu_capability",
        lambda: GpuCapabilityInfo(
            gpu_name="NVIDIA GeForce RTX 3060",
            compute_capability="8.6",
            cuda_arch_code="86",
            total_vram_mb=12288
        )
    )

    try:
        flags = get_llama_build_flags(cpuinfo_path=temp_path)
        assert "-DGGML_CUDA=ON" in flags.cmake_args_list
        assert "-DGGML_AVX=ON" in flags.cmake_args_list
        assert "-DGGML_AVX2=ON" in flags.cmake_args_list
        assert "-DGGML_F16C=ON -DGGML_FMA=ON" in flags.cmake_args_str
        assert "-DCMAKE_CUDA_ARCHITECTURES=86" in flags.cmake_args_list
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)



def test_cli_output(capsys):
    """T013 [US3]: Verifies CLI report output function."""
    from src.core.cpu_detector import print_detection_report
    print_detection_report()
    captured = capsys.readouterr()
    assert "vllm_serv 하드웨어 감지 및 llama.cpp 빌드 리포트" in captured.out
    assert "생성된 CMake 인자:" in captured.out


def test_match_platform_profile(monkeypatch):
    """T008 & T010: Verifies match_platform_profile returns correct profile ID based on GPU compute capability & CPU AVX2."""
    from src.core.cpu_detector import match_platform_profile, GpuCapabilityInfo, CpuFeatureInfo

    # Case 1: sm_61 + AVX2 CPU (e.g. Haswell Xeon E3-1231 v3 + GTX 1080 Ti)
    monkeypatch.setattr(
        "src.core.cpu_detector.detect_gpu_capability",
        lambda: GpuCapabilityInfo(
            gpu_name="GeForce GTX 1080 Ti",
            compute_capability="6.1",
            cuda_arch_code="61",
            total_vram_mb=11264
        )
    )
    monkeypatch.setattr(
        "src.core.cpu_detector.detect_cpu_features",
        lambda cpuinfo_path="/proc/cpuinfo": CpuFeatureInfo(
            model_name="Intel Xeon E3-1231 v3",
            architecture="x86_64",
            supports_avx=True,
            supports_avx2=True,
            supports_f16c=True,
            supports_fma=True
        )
    )
    assert match_platform_profile() == "pascal-avx2-gtx1080ti"

    # Case 2: sm_61 + Legacy CPU (no AVX, e.g. i7 930)
    monkeypatch.setattr(
        "src.core.cpu_detector.detect_cpu_features",
        lambda cpuinfo_path="/proc/cpuinfo": CpuFeatureInfo(
            model_name="Intel Core i7 930",
            architecture="x86_64",
            supports_avx=False,
            supports_avx2=False,
            supports_f16c=False,
            supports_fma=False
        )
    )
    assert match_platform_profile() == "legacy-i7-930-gtx1070"

    # Case 3: sm_86 + Modern CPU
    monkeypatch.setattr(
        "src.core.cpu_detector.detect_gpu_capability",
        lambda: GpuCapabilityInfo(
            gpu_name="GeForce RTX 3060",
            compute_capability="8.6",
            cuda_arch_code="86",
            total_vram_mb=12288
        )
    )
    monkeypatch.setattr(
        "src.core.cpu_detector.detect_cpu_features",
        lambda cpuinfo_path="/proc/cpuinfo": CpuFeatureInfo(
            model_name="Modern x86_64 CPU",
            architecture="x86_64",
            supports_avx=True,
            supports_avx2=True
        )
    )
    assert match_platform_profile() == "dev-rtx3060"



def test_check_hardware_preflight():
    """T005: Verifies check_hardware_preflight structure and execution."""
    from src.core.cpu_detector import check_hardware_preflight
    res = check_hardware_preflight()
    assert "passed" in res
    assert "nvidia_smi" in res
    assert "nvcc" in res


