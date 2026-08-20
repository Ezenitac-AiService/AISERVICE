#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AISERVICE Offline Model Weights Exporter (export_offline_models.py)
------------------------------------------------------------------
Packages AI model weights (Qwen3.5 LLM, BGE-M3, BGE-Reranker, Prompt-Guard)
into migration_pack/models/ for air-gapped / offline deployments.
"""

import sys
import os
import shutil
import tarfile
import argparse
from datetime import datetime

# Windows Console UTF-8 safety
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(PACK_ROOT, ".."))
MODELS_EXPORT_DIR = os.path.join(PACK_ROOT, "models")

LOCAL_MODEL_DIRS = [
    os.path.join(PROJECT_ROOT, "model_gateway", "models"),
    os.path.join(PROJECT_ROOT, "ateam", "pilos-sentiment-index", "artifacts"),
]


def export_models():
    os.makedirs(MODELS_EXPORT_DIR, exist_ok=True)
    print("=" * 70)
    print(" [AISERVICE] OFFLINE MODEL WEIGHTS EXPORTER (Air-Gapped Pack)")
    print(f" Timestamp: {datetime.now().isoformat()}")
    print(f" Destination: {MODELS_EXPORT_DIR}")
    print("=" * 70)

    copied_count = 0
    total_bytes = 0

    for src_dir in LOCAL_MODEL_DIRS:
        if not os.path.exists(src_dir):
            continue
        rel = os.path.relpath(src_dir, PROJECT_ROOT)
        print(f"\n▶ Scanning '{rel}'...")
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                src_file = os.path.join(root, file)
                rel_file = os.path.relpath(src_file, PROJECT_ROOT)
                dest_file = os.path.join(MODELS_EXPORT_DIR, rel_file)
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                if not os.path.exists(dest_file):
                    shutil.copy2(src_file, dest_file)
                    sz = os.path.getsize(src_file)
                    total_bytes += sz
                    copied_count += 1
                    print(f"  ✓ Exported: {rel_file} ({sz / (1024*1024):.1f} MB)")

    print("-" * 70)
    print(f" Summary: Exported {copied_count} files ({total_bytes / (1024*1024):.1f} MB)")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="AISERVICE Offline Model Weights Exporter")
    args = parser.parse_args()
    export_models()


if __name__ == "__main__":
    main()
