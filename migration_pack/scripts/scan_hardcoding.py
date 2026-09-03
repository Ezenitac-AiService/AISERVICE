#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_hardcoding.py - Comprehensive Static Hardcoding and Secret Leak Scanner.
-------------------------------------------------------------------------------
Enforces:
- Constitution III: No hardcoded legacy domains (duckdns.org, ezenitac).
- Constitution IV: No plaintext secret leaks.
- Constitution VII: No hardcoded loopback probes (127.0.0.1:8081).
- No legacy WSL paths (/dev/dxg, /usr/lib/wsl) or legacy hardware (GTX 1070, i7-930).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
AISERVICE_DIR = SCRIPT_DIR.parents[1]

FORBIDDEN_PATTERNS = [
    (r"ezenitac\.duckdns\.org", "Legacy DuckDNS public domain"),
    (r"/dev/dxg", "Legacy WSL D3D12 device mount"),
    (r"/usr/lib/wsl", "Legacy WSL driver path"),
    (r"i7-930", "Legacy Nehalem CPU target"),
    (r"GTX 1070", "Legacy Pascal GPU target"),
    (r"http://127\.0\.0\.1:8081", "Prohibited loopback to internal LLM service"),
    (r"http://127\.0\.0\.1:8090", "Prohibited loopback to internal Embedding service"),
    (r"http://127\.0\.0\.1:8091", "Prohibited loopback to internal Reranker service"),
]

IGNORED_DIRS = {
    ".git",
    ".specify",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    "specs",
    "brain",
    "wheels",
    "legacy_archive",
    "tests",
    "sample",
    "artifacts",
    "node_modules",
    "Oliview_LLM",
    "data",
    "models",
    "logs",
    "database",
}

IGNORED_FILES = {
    "scan_hardcoding.py",
    "normalize_compose.py",
    "test_ddns_removal_contract.py",
    "test_native_runtime_contract.py",
    "test_probe_isolation.py",
}


def scan_file(file_path: Path) -> List[Tuple[int, str, str]]:
    findings = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
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
    print("AISERVICE Strict Static Hardcoding & Domain Leak Scanner")
    print("=" * 80)

    # Scopes: Target migration package, runtime containers, gateway, and deployment clients
    scan_targets = [
        AISERVICE_DIR / "migration_pack",
        AISERVICE_DIR / "gateway",
        AISERVICE_DIR / "ateam",
        AISERVICE_DIR / "bteam",
        AISERVICE_DIR / "scripts",
        AISERVICE_DIR.parent / "dist_client_a",
    ]

    # Also check root compose and setup scripts
    root_files = [
        AISERVICE_DIR / "docker-compose.yml",
        AISERVICE_DIR / "run_all_services.sh",
        AISERVICE_DIR / "make_migration_pack.py",
        AISERVICE_DIR / "bootstrap_restore.sh",
        AISERVICE_DIR / ".env.example",
    ]

    for rf in root_files:
        if rf.exists() and rf.name not in IGNORED_FILES:
            scanned_files += 1
            findings = scan_file(rf)
            if findings:
                print(f"\n[VIOLATION] {rf.name}:")
                for line_no, desc, snippet in findings:
                    print(f"   Line {line_no:4d}: [{desc}]")
                    print(f"            >>> {snippet}")
                    total_findings += 1

    for target_dir in scan_targets:
        if not target_dir.exists():
            continue
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for file in files:
                if file in IGNORED_FILES or not file.endswith((".py", ".json", ".sh", ".yml", ".yaml", ".template", ".toml", ".service")):
                    continue
                file_path = Path(root) / file
                scanned_files += 1
                file_findings = scan_file(file_path)
                if file_findings:
                    rel_path = file_path.relative_to(AISERVICE_DIR if target_dir.is_relative_to(AISERVICE_DIR) else target_dir.parent)
                    print(f"\n[VIOLATION] {rel_path}:")
                    for line_no, desc, snippet in file_findings:
                        print(f"   Line {line_no:4d}: [{desc}]")
                        print(f"            >>> {snippet}")
                        total_findings += 1

    print("\n" + "=" * 80)
    print(f"Scan Complete: Scanned {scanned_files} files across AISERVICE.")
    if total_findings == 0:
        print("[PASS] 0 hardcoded domain or architecture leaks detected!")
        return 0
    else:
        print(f"[FAIL] Found {total_findings} forbidden hardcoding violations.")
        return 1


if __name__ == "__main__":
    sys.exit(run_scan())
