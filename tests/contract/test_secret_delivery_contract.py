"""Contract tests for secure secret delivery and packaging exclusions (T054).

Enforces:
- Constitution IV: Plaintext secret exclusion in distribution archives.
- FR-009: 0600 file permissions and secure external delivery path.
"""

from pathlib import Path
import pytest
from AISERVICE.migration_pack.scripts.configure_env import validate_secret_file_permissions

def test_secret_file_mode_0600_check(tmp_path: Path):
    safe_file = tmp_path / ".env.secret"
    safe_file.write_text("DB_PASSWORD=secret", encoding="utf-8")
    safe_file.chmod(0o600)

    assert validate_secret_file_permissions(safe_file) is True

    unsafe_file = tmp_path / ".env.insecure"
    unsafe_file.write_text("DB_PASSWORD=secret", encoding="utf-8")
    unsafe_file.chmod(0o644)

    with pytest.raises(PermissionError, match="0600"):
        validate_secret_file_permissions(unsafe_file)
