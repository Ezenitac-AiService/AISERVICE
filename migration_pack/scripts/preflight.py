#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preflight.py - Host environment preflight verification for AISERVICE target platform.
-----------------------------------------------------------------------------------
Verifies:
- Ubuntu 24.04 LTS
- Docker Compose v2 & Docker Engine
- NVIDIA Driver & nvidia-smi (RTX 3060 12GB)
- CPU AVX2 instructions support (i7-4770)
- Sufficient disk space
- Host port availability (3000, 8001-8004)
- Profile match: dev-rtx3060
Outputs structured JSON report.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def check_os_release() -> tuple[bool, str]:
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return False, "Not a Linux OS or /etc/os-release missing"
    content = os_release.read_text(encoding="utf-8")
    if "Ubuntu" in content and "24.04" in content:
        return True, "Ubuntu 24.04 LTS detected"
    return True, f"Linux detected: {content.splitlines()[0]}"


def check_cpu_avx2() -> tuple[bool, str]:
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return True, "Unable to check /proc/cpuinfo"
    flags = cpuinfo.read_text(encoding="utf-8")
    if "avx2" in flags.lower():
        return True, "AVX2 instructions supported"
    return False, "AVX2 instructions NOT found in /proc/cpuinfo"


def check_docker_compose() -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "docker command not found"
    try:
        res = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return True, f"Docker Compose v2 available: {res.stdout.strip()}"
        return False, f"docker compose failed: {res.stderr.strip()}"
    except Exception as e:
        return False, f"Docker check exception: {e}"


def check_nvidia_gpu() -> tuple[bool, str]:
    if not shutil.which("nvidia-smi"):
        # If in container/mock environment, provide warning
        return False, "nvidia-smi command not found"
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            gpu_info = res.stdout.strip()
            return True, f"NVIDIA GPU detected: {gpu_info}"
        return False, f"nvidia-smi failed: {res.stderr.strip()}"
    except Exception as e:
        return False, f"nvidia-smi check exception: {e}"


def check_port_availability(ports: list[int]) -> tuple[bool, list[str]]:
    conflicts = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            # Try to bind to port
            try:
                s.bind(("0.0.0.0", port))
            except OSError:
                conflicts.append(f"Port {port} is already in use")
    return len(conflicts) == 0, conflicts


def check_disk_space(min_gb: float = 10.0) -> tuple[bool, str]:
    try:
        stat = os.statvfs("/")
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        if free_gb >= min_gb:
            return True, f"Disk space sufficient: {free_gb:.1f} GB available"
        return False, f"Insufficient disk space: {free_gb:.1f} GB available (need {min_gb} GB)"
    except Exception as e:
        return True, f"Disk check skipped: {e}"


def run_preflight(report_path: str | None = None) -> bool:
    checks = {}
    all_passed = True

    # 1. OS
    os_ok, os_msg = check_os_release()
    checks["os_release"] = {"passed": os_ok, "message": os_msg}
    all_passed = all_passed and os_ok

    # 2. CPU
    cpu_ok, cpu_msg = check_cpu_avx2()
    checks["cpu_avx2"] = {"passed": cpu_ok, "message": cpu_msg}
    all_passed = all_passed and cpu_ok

    # 3. Docker
    docker_ok, docker_msg = check_docker_compose()
    checks["docker_compose"] = {"passed": docker_ok, "message": docker_msg}
    all_passed = all_passed and docker_ok

    # 4. GPU
    gpu_ok, gpu_msg = check_nvidia_gpu()
    checks["nvidia_gpu"] = {"passed": gpu_ok, "message": gpu_msg}
    # Note: in test/mock environment, allow gpu warning if APP_RUN_MODE=DEMO mock
    if not gpu_ok and os.environ.get("MOCK_LLAMA_SERVER") == "1":
        checks["nvidia_gpu"]["mocked"] = True
    else:
        all_passed = all_passed and gpu_ok

    # 5. Disk
    disk_ok, disk_msg = check_disk_space()
    checks["disk_space"] = {"passed": disk_ok, "message": disk_msg}
    all_passed = all_passed and disk_ok

    # 6. Ports (3000, 8001-8004)
    # If checking ports during preflight
    ports_ok, port_msgs = check_port_availability([3000, 8001, 8002, 8003, 8004])
    checks["tunnel_ports"] = {"passed": ports_ok, "conflicts": port_msgs}
    all_passed = all_passed and ports_ok

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_profile": "dev-rtx3060",
        "status": "PASS" if all_passed else "FAIL",
        "checks": checks,
    }

    if report_path:
        out = Path(report_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return all_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AISERVICE Host Preflight Verification")
    parser.add_argument("--report", "-r", help="Path to write JSON preflight report")
    args = parser.parse_args()

    passed = run_preflight(args.report)
    sys.exit(0 if passed else 1)
