import sys
from pathlib import Path
import tempfile
import pytest
import tarfile
import json
import io

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from scripts.pack_secrets import (
    discover_secrets,
    pack_secrets,
    compute_sha256,
)
from scripts.restore_secrets import (
    restore_secrets,
    load_archive,
)


def test_discover_secrets_real_workspace():
    """Verifies that discover_secrets finds root .env, bteam/.env, and ddns/duckdns-config.xml."""
    secrets = discover_secrets(WORKSPACE_ROOT)
    secret_rel_paths = [p.relative_to(WORKSPACE_ROOT).as_posix() for p in secrets]

    assert ".env" in secret_rel_paths
    assert "bteam/.env" in secret_rel_paths
    assert "ddns/duckdns-config.xml" in secret_rel_paths
    assert "ateam/pilos-sentiment-index/.env" in secret_rel_paths
    assert "model_gateway/.env" in secret_rel_paths


def test_pack_and_restore_roundtrip_mock():
    """Tests end-to-end packaging and restoration in an isolated temporary directory."""
    with tempfile.TemporaryDirectory() as tmp_src_dir, tempfile.TemporaryDirectory() as tmp_dest_dir:
        src_root = Path(tmp_src_dir)
        dest_root = Path(tmp_dest_dir)

        # 1. Setup mock secret structure
        (src_root / ".env").write_text("SECRET_A=val_a\n", encoding="utf-8")
        (src_root / "bteam").mkdir()
        (src_root / "bteam" / ".env").write_text("SECRET_B=val_b\n", encoding="utf-8")
        (src_root / "ddns").mkdir()
        (src_root / "ddns" / "duckdns-config.xml").write_text("<config><token>test</token></config>", encoding="utf-8")

        # 2. Pack
        tar_output = src_root / "test_pack.tar.gz"
        packed_path, manifest = pack_secrets(root_dir=src_root, output_tar=tar_output)
        assert packed_path.exists()
        assert manifest["file_count"] == 3

        # 3. Restore into clean dest_root
        results = restore_secrets(archive_path=packed_path, target_root=dest_root, backup_existing=False)
        assert len(results) == 3

        # 4. Assert roundtrip hashes
        for rel_path, meta in manifest["files"].items():
            restored_file = dest_root / rel_path
            assert restored_file.exists(), f"{rel_path} was not restored"
            assert compute_sha256(restored_file) == meta["sha256"], f"Hash mismatch on {rel_path}"


def test_tamper_detection():
    """Verifies that restore_secrets detects tampered archive payload and aborts."""
    with tempfile.TemporaryDirectory() as tmp_src_dir, tempfile.TemporaryDirectory() as tmp_dest_dir:
        src_root = Path(tmp_src_dir)
        dest_root = Path(tmp_dest_dir)

        (src_root / ".env").write_text("ORIGINAL_SECRET=123\n", encoding="utf-8")
        tar_output = src_root / "tampered.tar.gz"

        # Create valid pack first
        pack_secrets(root_dir=src_root, output_tar=tar_output)

        # Tamper payload while keeping original manifest
        manifest, files_data = load_archive(tar_output)
        files_data[".env"] = b"TAMPERED_SECRET=999\n"

        # Re-save with tampered payload
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        with tarfile.open(tar_output, "w:gz") as tar:
            tarinfo = tarfile.TarInfo(name="secrets_manifest.json")
            tarinfo.size = len(manifest_bytes)
            tar.addfile(tarinfo, io.BytesIO(manifest_bytes))

            for rel_path, data in files_data.items():
                tarinfo = tarfile.TarInfo(name=f"secrets/{rel_path}")
                tarinfo.size = len(data)
                tar.addfile(tarinfo, io.BytesIO(data))

        # Attempt restore -> must raise ValueError
        with pytest.raises(ValueError, match="Integrity check failed"):
            restore_secrets(archive_path=tar_output, target_root=dest_root)


def test_backup_existing_file():
    """Verifies that existing target files are backed up to .bak.<timestamp>."""
    with tempfile.TemporaryDirectory() as tmp_src_dir, tempfile.TemporaryDirectory() as tmp_dest_dir:
        src_root = Path(tmp_src_dir)
        dest_root = Path(tmp_dest_dir)

        (src_root / ".env").write_text("NEW_SECRET=456\n", encoding="utf-8")
        (dest_root / ".env").write_text("OLD_SECRET=123\n", encoding="utf-8")

        tar_output = src_root / "backup_test.tar.gz"
        pack_secrets(root_dir=src_root, output_tar=tar_output)

        restore_secrets(archive_path=tar_output, target_root=dest_root, backup_existing=True)

        assert (dest_root / ".env").read_text(encoding="utf-8") == "NEW_SECRET=456\n"
        backup_files = list(dest_root.glob(".env.bak.*"))
        assert len(backup_files) == 1
        assert backup_files[0].read_text(encoding="utf-8") == "OLD_SECRET=123\n"
