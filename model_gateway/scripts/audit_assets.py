#!/usr/bin/env python3
"""
Asset inventory scanner and legacy archiver script.
(090-audit-test-refactor: US1)
"""
import os
import shutil
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = REPO_ROOT / ".legacy" / "archive_088_sync"

# Patterns of files/directories to inspect for duplicates or legacy items
KNOWN_TARGET_DIRS = ["scripts", "src", "samples", "wheels", "tests"]


def scan_inventory():
    inventory = []
    
    # Ensure archive dir exists
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    
    for target in KNOWN_TARGET_DIRS:
        dir_path = REPO_ROOT / target
        if not dir_path.exists():
            continue
            
        for path in dir_path.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(REPO_ROOT)
                name = path.name
                
                # Classification rules
                action = "PRESERVE"
                status = "ACTIVE"
                
                # Check for legacy backup or temporary files
                if name.endswith(".bak") or name.endswith(".tmp") or "~" in name or name.startswith(".#"):
                    status = "LEGACY_REPLACED"
                    action = "ARCHIVE_TO_LEGACY"
                elif "dup" in name.lower() or "legacy_tmp" in name.lower():
                    status = "DUPLICATE"
                    action = "ARCHIVE_TO_LEGACY"
                
                inventory.append({
                    "file_path": str(rel_path),
                    "name": name,
                    "status": status,
                    "action": action
                })
                
    return inventory


def archive_legacy_items(inventory, dry_run=False):
    archived_count = 0
    for item in inventory:
        if item["action"] == "ARCHIVE_TO_LEGACY":
            src_file = REPO_ROOT / item["file_path"]
            dst_file = ARCHIVE_DIR / item["file_path"]
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            
            if not dry_run:
                shutil.move(str(src_file), str(dst_file))
                item["status"] = "ARCHIVED"
                item["target_path"] = str(dst_file.relative_to(REPO_ROOT))
            archived_count += 1
            
    return archived_count


def generate_report(inventory, report_file=None):
    report = {
        "total_files_scanned": len(inventory),
        "preserved_files": len([i for i in inventory if i["action"] == "PRESERVE"]),
        "archived_files": len([i for i in inventory if i["action"] == "ARCHIVE_TO_LEGACY" or i["status"] == "ARCHIVED"]),
        "inventory": inventory
    }
    
    if report_file:
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
    return report


if __name__ == "__main__":
    inv = scan_inventory()
    count = archive_legacy_items(inv, dry_run=False)
    rep = generate_report(inv, REPO_ROOT / "specs" / "090-audit-test-refactor" / "audit_report.json")
    print(f"[AUDIT] Scan completed. Scanned: {rep['total_files_scanned']}, Preserved: {rep['preserved_files']}, Archived to .legacy: {count}")
