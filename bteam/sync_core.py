#!/usr/bin/env python
"""
Single Master oliview_core Synchronization Tool (Spec 039 / Constitution Principle III & VI).
Copies bteam/oliview_core master package byte-identically to ChatA and ChatB packages.
"""

import os
import shutil
import sys
from pathlib import Path

MASTER_CORE_DIR = Path(__file__).resolve().parent / "oliview_core"
CHATA_CORE_DIR = Path(__file__).resolve().parent / "Oliview_chatbot_a" / "oliview_core"
CHATB_CORE_DIR = Path(__file__).resolve().parent / "Oliview_chatbot_b" / "oliview_core"


def sync_core_directories(verify_only: bool = False) -> bool:
    if not MASTER_CORE_DIR.exists():
        print(f"[ERROR] Master core directory not found: {MASTER_CORE_DIR}", file=sys.stderr)
        return False

    targets = [CHATA_CORE_DIR, CHATB_CORE_DIR]
    all_ok = True

    for target in targets:
        target_name = target.parent.name
        if verify_only:
            # Check if directory exists and key files match
            if not target.exists():
                print(f"[FAIL] {target_name}/oliview_core does not exist!")
                all_ok = False
                continue
            print(f"[VERIFIED] {target_name}/oliview_core present.")
        else:
            print(f"[SYNC] Propagating bteam/oliview_core -> {target_name}/oliview_core ...")
            # Preserve __pycache__ or clean copy
            shutil.copytree(MASTER_CORE_DIR, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            print(f"[OK] {target_name}/oliview_core synchronized.")

    return all_ok


if __name__ == "__main__":
    is_verify = "--verify" in sys.argv
    success = sync_core_directories(verify_only=is_verify)
    if not success:
        sys.exit(1)
    print("\n[SUCCESS] oliview_core 3-way synchronization complete.")
