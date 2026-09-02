#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize_compose.py
====================
Windows WSL2 전용 디바이스(/dev/dxg, /usr/lib/wsl) 및 특수 볼륨을
Native Ubuntu Linux 호환 표준 Docker Compose v2 형식으로 자동 정규화하는 변환기.
외부 의존성 없이 표준 라이브러리(re, os, sys)만으로 동작하여 클린 OS에서도 즉시 실행 가능.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def normalize_compose_content(
    content: str,
    preserve_external_volumes: bool = False,
    cpu_only: bool = False,
) -> str:
    """
    docker-compose.yml 텍스트를 읽어 우분투 네이티브 리눅스에 맞게 정규화합니다.
    1. /usr/lib/wsl 볼륨 마운트 제거
    2. /dev/dxg 디바이스 마운트 제거
    3. WSL 전용 LD_LIBRARY_PATH 정규화
    4. external: true 볼륨을 안전하게 일반 named volume으로 승격 (선택적)
    5. deploy.resources.reservations.devices GPU 디렉티브 보장
    """
    lines = content.splitlines()
    output_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # CPU-only 모드에서는 GPU deploy 블록 전체를 제거합니다.
        if cpu_only and re.match(r"^\s*deploy:\s*$", line):
            deploy_indent = len(line) - len(line.lstrip())
            end = i + 1
            block = []
            while end < len(lines):
                candidate = lines[end]
                if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= deploy_indent:
                    break
                block.append(candidate)
                end += 1
            block_text = "\n".join(block).lower()
            if "nvidia" in block_text or "capabilities: [gpu]" in block_text:
                i = end
                continue

        if cpu_only and re.search(
            r"(?:NVIDIA_VISIBLE_DEVICES|NVIDIA_DRIVER_CAPABILITIES|runtime:\s*nvidia)",
            line,
            re.IGNORECASE,
        ):
            i += 1
            continue

        # 1. /usr/lib/wsl 마운트 라인 건너뛰기
        if re.search(r'-\s+/usr/lib/wsl', line):
            i += 1
            continue

        # 2. devices: /dev/dxg 블록 건너뛰기
        if re.match(r'^\s*devices:\s*$', line):
            # 다음 라인이 /dev/dxg 인지 검사
            if i + 1 < len(lines) and re.search(r'/dev/dxg', lines[i + 1]):
                i += 2
                continue

        if re.search(r'-\s+/dev/dxg', line):
            i += 1
            continue

        # 3. LD_LIBRARY_PATH 정규화 (WSL 경로 제거)
        if "LD_LIBRARY_PATH=" in line and "/usr/lib/wsl" in line:
            line = re.sub(
                r'LD_LIBRARY_PATH=[^"\']+',
                'LD_LIBRARY_PATH=/usr/local/lib:/usr/lib/x86_64-linux-gnu',
                line
            )

        # 4. external: true 볼륨 안전 처리 (Ubuntu에서 볼륨 없을 시 크래시 방지)
        if not preserve_external_volumes:
            if re.match(r'^\s*external:\s*true', line):
                # external: true를 주석 처리하거나 건너뜀
                i += 1
                continue

        output_lines.append(line)
        i += 1

    result = "\n".join(output_lines) + "\n"

    # 5. CPU-only 환경은 GPU 런타임을 제거하고 애플리케이션에 명시적으로 전달합니다.
    if cpu_only and "vllm-serv:" in result:
        if "MODEL_GATEWAY_CPU_ONLY=1" not in result:
            result = result.replace(
                "    environment:\n",
                "    environment:\n"
                "      - AISERVICE_SKIP_GPU=1\n"
                "      - MODEL_GATEWAY_CPU_ONLY=1\n",
                1,
            )
        return result

    # 6. vllm-serv GPU deploy 디렉티브 보장 (만약 deploy가 없으면 주입)
    if "deploy:" not in result and "vllm-serv:" in result:
        gpu_deploy_block = (
            "    deploy:\n"
            "      resources:\n"
            "        reservations:\n"
            "          devices:\n"
            "            - driver: nvidia\n"
            "              count: all\n"
            "              capabilities: [gpu]\n"
        )
        # image: vllm-serv 또는 container_name: vllm-serv-gateway 아래에 주입
        if "container_name: vllm-serv-gateway" in result:
            result = result.replace(
                "container_name: vllm-serv-gateway",
                "container_name: vllm-serv-gateway\n" + gpu_deploy_block
            )

    return result


def normalize_file(
    input_file: Path | str,
    output_file: Path | str | None = None,
    *,
    cpu_only: bool = False,
) -> Path:
    """단일 compose 파일을 정규화하여 출력 파일로 저장합니다."""
    in_path = Path(input_file)
    if not in_path.is_file():
        raise FileNotFoundError(f"Compose file not found: {in_path}")

    out_path = Path(output_file) if output_file else in_path

    with open(in_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    normalized = normalize_compose_content(raw_content, cpu_only=cpu_only)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Normalize docker-compose.yml for Native Ubuntu Linux")
    parser.add_argument("--input", "-i", default="docker-compose.yml", help="Input compose file path")
    parser.add_argument("--output", "-o", default=None, help="Output compose file path (default: overwrite input)")
    parser.add_argument(
        "--cpu-only",
        action="store_true",
        help="GPU deploy/device 설정을 제거하고 Model Gateway CPU-only 모드로 정규화",
    )
    args = parser.parse_args()

    out = normalize_file(args.input, args.output, cpu_only=args.cpu_only)
    print(f"[OK] Normalized compose saved to: {out}")


if __name__ == "__main__":
    main()
