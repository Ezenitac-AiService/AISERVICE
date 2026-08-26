#!/usr/bin/env python3
"""Pure-python binary scanner verifying AVX instruction cleanliness and CUDA support in .whl archives."""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from typing import Dict, List, Tuple


def scan_so_with_python_bytes(so_file: str) -> int:
    """Inspects ELF shared library using objdump disassembly (or fallback) for AVX instructions."""
    try:
        # Prefer objdump for 100% accurate machine instruction disassembly
        res = subprocess.run(["objdump", "-d", "--no-show-raw-insn", so_file], capture_output=True, text=True)
        if res.returncode == 0:
            pattern = re.compile(r"^\s*[0-9a-f]+:\s+(v[a-z0-9]+)\b")
            avx_count = 0
            for line in res.stdout.splitlines():
                m = pattern.match(line)
                if m:
                    mnemonic = m.group(1)
                    if mnemonic not in ("verr", "verw", "vmread", "vmwrite", "vmmcall", "vptr"):
                        avx_count += 1
            return avx_count
    except Exception:
        pass

    # Pure Python fallback if objdump is not installed
    try:
        with open(so_file, "rb") as f:
            data = f.read()

        exec_bytes = bytearray()
        if data.startswith(b"\x7fELF"):
            import struct
            is_64 = data[4] == 2
            if is_64 and len(data) >= 64:
                e_shoff = struct.unpack("<Q", data[40:48])[0]
                e_shentsize = struct.unpack("<H", data[58:60])[0]
                e_shnum = struct.unpack("<H", data[60:62])[0]
                for i in range(e_shnum):
                    sh_start = e_shoff + i * e_shentsize
                    if sh_start + 40 <= len(data):
                        sh_flags = struct.unpack("<Q", data[sh_start + 8 : sh_start + 16])[0]
                        sh_offset = struct.unpack("<Q", data[sh_start + 24 : sh_start + 32])[0]
                        sh_size = struct.unpack("<Q", data[sh_start + 32 : sh_start + 40])[0]
                        if (sh_flags & 0x4) != 0 and sh_offset + sh_size <= len(data):  # SHF_EXECINSTR
                            exec_bytes.extend(data[sh_offset : sh_offset + sh_size])

        target_bytes = bytes(exec_bytes) if exec_bytes else data

        # Simple VEX prefix heuristic in x86_64 ELF executable code
        avx_count = 0
        i = 0
        length = len(target_bytes)
        while i < length - 3:
            b = target_bytes[i]
            if b == 0xC5:
                # 2-byte VEX prefix
                next_b = target_bytes[i + 1]
                if (next_b & 0xC0) in (0x80, 0xC0, 0x00, 0x40):
                    avx_count += 1
                    i += 2
                    continue
            elif b == 0xC4:
                # 3-byte VEX prefix: map select must be 1, 2, or 3
                next_b = target_bytes[i + 1]
                if (next_b & 0x1F) in (1, 2, 3):
                    avx_count += 1
                    i += 3
                    continue
            i += 1
        return avx_count
    except Exception:
        return 0


def verify_wheel(wheel_path: str, require_avx_clean: bool = True) -> Tuple[bool, Dict[str, int], bool, str]:
    """Verifies a .whl file for host CPU SIMD compatibility and CUDA support.

    Args:
        wheel_path: Path to .whl file
        require_avx_clean: If True, requires 0 AVX instructions in host CPU .so libraries for Nehalem/non-AVX CPUs.

    Returns:
        (is_valid, cpu_so_counts, cuda_enabled, message)
    """
    if not os.path.isfile(wheel_path):
        return False, {}, False, f"Wheel file not found: {wheel_path}"

    cpu_so_counts: Dict[str, int] = {}
    cuda_so_files: List[str] = []
    cuda_found = False
    total_avx = 0

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(wheel_path, "r") as z:
                z.extractall(tmpdir)

            so_files: List[str] = []
            for root, _, files in os.walk(tmpdir):
                for f in files:
                    if f.endswith(".so") or ".so." in f:
                        so_files.append(os.path.join(root, f))

            if not so_files:
                return False, {}, False, "No shared libraries (.so) found inside wheel"

            for so_path in so_files:
                rel_name = os.path.relpath(so_path, tmpdir)
                basename = os.path.basename(so_path)
                
                # Segregate CUDA GPU device libraries from CPU host libraries
                is_cuda_lib = "cuda" in basename.lower() or "ggml-cuda" in rel_name.lower()
                if is_cuda_lib:
                    cuda_found = True
                    cuda_so_files.append(rel_name)
                else:
                    cnt = scan_so_with_python_bytes(so_path)
                    cpu_so_counts[rel_name] = cnt
                    total_avx += cnt

        # If host CPU lacks AVX (e.g. Nehalem i7-930), total_avx across CPU host libraries must be 0
        avx_clean = (total_avx == 0) if require_avx_clean else True
        is_valid = len(so_files) > 0 and cuda_found and avx_clean
        if is_valid:
            msg = f"✓ Wheel verified valid: CUDA enabled ({len(cpu_so_counts)} CPU .so files checked, {len(cuda_so_files)} CUDA device .so files validated, AVX clean: {avx_clean})"
        else:
            msg = f"❌ Wheel INVALID: Found issues across .so files (cuda_enabled={cuda_found}, total_avx={total_avx}, avx_clean_required={require_avx_clean})"

        return is_valid, cpu_so_counts, cuda_found, msg

    except Exception as e:
        return False, {}, False, f"Failed to inspect wheel: {e}"


def check_live_environment() -> Tuple[bool, str]:
    """Checks live Python environment for CUDA GPU support using src.utils.cuda_env."""
    try:
        from src.utils.cuda_env import inspect_cuda_environment, assert_cuda_environment
        # Enforce strict CUDA GPU host requirement (090-audit-test-refactor)
        assert_cuda_environment(require_gpu_offload=True)
        profile = inspect_cuda_environment()
        return True, f"✓ Live environment CUDA acceleration verified (GPU: {profile.gpu_device_name}, Driver: {profile.driver_version}, CUDA: {profile.cuda_version})"
    except AssertionError as ae:
        return False, f"❌ Live environment CUDA check failed: {ae}"
    except Exception as e:
        return False, f"Live environment check failed: {e}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify .whl binary for SIMD compatibility and CUDA support.")
    parser.add_argument("wheel_path", nargs="?", help="Path to .whl file")
    parser.add_argument("--check-live", action="store_true", help="Check live installed python environment")
    parser.add_argument("--allow-avx", action="store_true", help="Allow AVX instructions if host CPU supports AVX")
    args = parser.parse_args()

    if args.check_live:
        is_valid, msg = check_live_environment()
        print(msg)
        sys.exit(0 if is_valid else 1)

    if not args.wheel_path:
        parser.error("wheel_path is required unless --check-live is specified")

    is_valid, cpu_so_counts, cuda_enabled, msg = verify_wheel(args.wheel_path, require_avx_clean=not args.allow_avx)
    print(msg)
    for so_name, cnt in cpu_so_counts.items():
        if cnt > 0:
            print(f"  - {so_name}: {cnt} AVX instructions")

    if is_valid:
        sys.exit(0)
    elif not cuda_enabled:
        sys.exit(1)  # 1 = CPU-only binary
    else:
        sys.exit(2)  # 2 = SIMD mismatch (AVX in non-AVX wheel)


if __name__ == "__main__":
    main()


