#!/usr/bin/env python3
"""
Pre-flight Static Hardcoding Scanner for AISERVICE.
Scans model_gateway/, bteam/, ateam/, and tests/ for forbidden hardcoded model names,
static fallback strings, and shadowed configurations.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple

# Ensure stdout handles UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# Patterns to scan
FORBIDDEN_PATTERNS = [
    (r'body_json\.get\(["\']model["\']\)\s*or\s*["\']qwen3\.5-4b["\']', "Hardcoded fallback model in inference_api"),
    (r'current_model["\'],\s*["\']qwen3\.5-4b["\']\)', "Hardcoded fallback model in config_manager"),
    (r'CHAT_LLM_MODEL,\s*["\']qwen3\.5-4b["\']', "Hardcoded CHAT_LLM_MODEL in ateam scripts"),
    (r'device_name\s*=\s*["\']NVIDIA GeForce GTX 1070["\']', "Hardcoded device_name in health_api"),
    (r'def\s+\w+\(.*n_ctx:\s*int\s*=\s*4096', "Hardcoded n_ctx=4096 default function argument shadow"),
]

IGNORED_DIRS = {
    '.git', '.specify', 'venv', '__pycache__', '.pytest_cache', 'build', 'dist', 'specs', 'brain'
}

def scan_file(file_path: Path) -> List[Tuple[int, str, str]]:
    findings = []
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return findings

    lines = content.splitlines()
    for line_idx, line in enumerate(lines, 1):
        for pattern, desc in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                findings.append((line_idx, desc, line.strip()))
    return findings

def run_scan() -> int:
    total_findings = 0
    scanned_files = 0
    print("=" * 80)
    print("AISERVICE Static Hardcoding & Config Shadowing Scanner")
    print("=" * 80)

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for file in files:
            if not file.endswith(('.py', '.json', '.sh')):
                continue
            if 'scan_hardcoding.py' in file:
                continue
            file_path = Path(root) / file
            scanned_files += 1
            file_findings = scan_file(file_path)
            if file_findings:
                rel_path = file_path.relative_to(ROOT_DIR)
                print(f"\n[VIOLATION] {rel_path}:")
                for line_no, desc, snippet in file_findings:
                    print(f"   Line {line_no:4d}: [{desc}]")
                    print(f"            >>> {snippet}")
                    total_findings += 1

    print("\n" + "=" * 80)
    print(f"Scan Complete: Scanned {scanned_files} files.")
    if total_findings == 0:
        print("[PASS] 0 hardcoding or shadowing violations detected!")
        return 0
    else:
        print(f"[FOUND] {total_findings} hardcoding violations that must be eliminated in Spec 034.")
        return total_findings

if __name__ == "__main__":
    sys.exit(run_scan())
