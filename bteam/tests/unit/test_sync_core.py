"""
Unit test for Master oliview_core Synchronization Tool (Spec 048 / T020).
Validates:
1. SHA-256 hash manifest equality between master oliview_core and Chatbot A / Chatbot B directories.
2. sync_core_directories(verify_only=True) returns True.
"""

from pathlib import Path
from sync_core import (
    MASTER_CORE_DIR,
    CHATA_CORE_DIR,
    CHATB_CORE_DIR,
    compute_core_hash_manifest,
    sync_core_directories,
)


def test_master_core_hash_manifest_identical_across_chatbots():
    """Verify SHA-256 byte-identical parity across master and all chatbots."""
    master_manifest = compute_core_hash_manifest(MASTER_CORE_DIR)
    chata_manifest = compute_core_hash_manifest(CHATA_CORE_DIR)
    chatb_manifest = compute_core_hash_manifest(CHATB_CORE_DIR)

    assert len(master_manifest) > 0, "Master oliview_core manifest must not be empty"
    assert master_manifest == chata_manifest, "Chatbot A core must be byte-identical to master core"
    assert master_manifest == chatb_manifest, "Chatbot B core must be byte-identical to master core"


def test_sync_core_verification_function():
    """Verify sync_core_directories(verify_only=True) reports clean parity."""
    assert sync_core_directories(verify_only=True) is True
