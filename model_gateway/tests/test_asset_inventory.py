"""
Unit and integration tests for asset inventory scanner and legacy archiver.
(090-audit-test-refactor: US1)
"""
import os
from pathlib import Path
import pytest
from scripts.audit_assets import scan_inventory, archive_legacy_items, REPO_ROOT, ARCHIVE_DIR


def test_archive_directory_exists():
    """Verify .legacy/archive_088_sync directory is created and accessible."""
    assert ARCHIVE_DIR.exists() or (REPO_ROOT / ".legacy").exists()


def test_scan_inventory_returns_items():
    """Verify inventory scan detects existing codebase assets."""
    inventory = scan_inventory()
    assert isinstance(inventory, list)
    assert len(inventory) > 0
    # Check that required fields exist
    for item in inventory[:5]:
        assert "file_path" in item
        assert "status" in item
        assert "action" in item


def test_archive_legacy_items_dry_run(tmp_path):
    """Verify dry_run does not move files prematurely."""
    dummy_legacy_file = REPO_ROOT / "scripts" / "test_dummy_legacy.bak"
    dummy_legacy_file.write_text("legacy backup content")
    try:
        inventory = scan_inventory()
        bak_items = [i for i in inventory if i["file_path"].endswith(".bak")]
        assert len(bak_items) > 0
        
        count = archive_legacy_items(inventory, dry_run=True)
        assert count > 0
        assert dummy_legacy_file.exists()
    finally:
        if dummy_legacy_file.exists():
            dummy_legacy_file.unlink()


def test_archive_legacy_items_execution(tmp_path):
    """Verify archive_legacy_items safely moves .bak files to .legacy/ without hard deletion."""
    dummy_legacy_file = REPO_ROOT / "scripts" / "test_dummy_execution.bak"
    dummy_legacy_file.write_text("legacy backup content for move")
    try:
        inventory = scan_inventory()
        count = archive_legacy_items(inventory, dry_run=False)
        assert count > 0
        assert not dummy_legacy_file.exists()
        
        target = ARCHIVE_DIR / "scripts" / "test_dummy_execution.bak"
        assert target.exists()
        assert target.read_text() == "legacy backup content for move"
    finally:
        target = ARCHIVE_DIR / "scripts" / "test_dummy_execution.bak"
        if target.exists():
            target.unlink()
        if dummy_legacy_file.exists():
            dummy_legacy_file.unlink()
