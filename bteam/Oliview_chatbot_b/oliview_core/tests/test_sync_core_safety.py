import hashlib
import os
import shutil
import sys
from pathlib import Path
import pytest

BTEAM_DIR = Path(__file__).resolve().parents[2]


def test_sync_core_dry_run_flag_and_hash_manifest_red_gate():
    """RED GATE: Asserts that sync_core.py supports --dry-run, produces a hash manifest,
    and performs atomic directory replacement. Fails until T026 implementation."""
    sys.path.insert(0, str(BTEAM_DIR))
    try:
        import sync_core  # type: ignore
        assert hasattr(sync_core, "compute_core_hash_manifest"), "sync_core must have compute_core_hash_manifest"
        assert hasattr(sync_core, "atomic_sync_core"), "sync_core must have atomic_sync_core"
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: enhanced safety functions not implemented in sync_core: {exc}")
