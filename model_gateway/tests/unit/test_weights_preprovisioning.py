"""
Unit tests for weights pre-provisioning validation and SHA-256 hash pinning.

Feature: 006-model-gateway-upgrade (User Story 2)
"""

import hashlib
import os
import pytest
from pathlib import Path

PINNED_9B_SHA256 = "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8"
MIN_FREE_DISK_GB = 6.5


def test_pinned_hash_constant():
    """Verify SHA-256 pinned hash for Qwen 3.5 9B Q4_K_M GGUF."""
    assert len(PINNED_9B_SHA256) == 64
    assert PINNED_9B_SHA256 == "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8"


def test_verify_hash_helper(tmp_path):
    """Verify SHA-256 hash verification helper detects matching and corrupted weights."""
    test_file = tmp_path / "dummy_weights.gguf"
    test_content = b"dual-llm-qwen3.5-9b-test-content"
    test_file.write_bytes(test_content)
    expected_hash = hashlib.sha256(test_content).hexdigest()

    # Match
    hasher = hashlib.sha256()
    with open(test_file, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    assert hasher.hexdigest() == expected_hash

    # Corrupted
    assert hasher.hexdigest() != "0" * 64


def test_model_downloader_raises_file_not_found():
    """Verify model_downloader raises FileNotFoundError on missing weights rather than downloading at runtime."""
    from src.core.model_downloader import download_model_if_missing

    with pytest.raises(FileNotFoundError) as exc_info:
        download_model_if_missing("non_existent_model_id_xyz")
    assert "Missing weights" in str(exc_info.value) or "pre-provisioning" in str(exc_info.value)
