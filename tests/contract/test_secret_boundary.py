"""Contract tests for secret boundaries, file permissions, and redaction.

Enforces:
- FR-011: Secrets isolation, permissions (0600), owner validation, missing key detection.
- Constitution IV: Structured logging and strict masking of tokens, keys, passwords.
- Constitution VII: Explicit enablement flag for SSH standby tunnel (default false).
"""

from pathlib import Path
import os
import tempfile
import pytest

def test_secret_loader_rejects_insecure_permissions():
    """Secret loader must reject secret files that do not have 0600 permissions."""
    from AISERVICE.migration_pack.scripts.configure_env import validate_secret_file_permissions

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("DUMMY_SECRET=value\n")
        temp_path = f.name
    try:
        # Set permission to 0644 (world readable)
        os.chmod(temp_path, 0o644)
        with pytest.raises(PermissionError, match="insecure file permissions"):
            validate_secret_file_permissions(temp_path)

        # Set permission to 0600
        os.chmod(temp_path, 0o600)
        # Should pass permissions check (ignoring uid check in test mode if non-root)
        assert validate_secret_file_permissions(temp_path, require_root=False) is True
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def test_secret_loader_detects_missing_required_keys():
    """Secret loader must fail when required secret keys are absent."""
    from AISERVICE.migration_pack.scripts.configure_env import load_and_validate_secrets

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("PILOS_DB_PASSWORD=secret1\n") # Missing other required keys
        temp_path = f.name
    try:
        os.chmod(temp_path, 0o600)
        with pytest.raises(ValueError, match="Missing required secret keys"):
            load_and_validate_secrets(temp_path, require_root=False)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def test_ssh_standby_tunnel_default_false_and_explicit_enablement():
    """SSH standby tunnel must be disabled by default (false)."""
    from AISERVICE.migration_pack.scripts.configure_env import get_ssh_standby_status

    # When not set, default must be disabled
    status = get_ssh_standby_status({})
    assert status == "installed_disabled", f"Expected installed_disabled when unset, got {status}"

    status = get_ssh_standby_status({"ENABLE_SSH_STANDBY_TUNNEL": "false"})
    assert status == "installed_disabled"

    status = get_ssh_standby_status({"ENABLE_SSH_STANDBY_TUNNEL": "true", "GATEWAY_ENDPOINT_VALID": "true"})
    assert status == "enabled_running"

def test_redaction_masks_sensitive_tokens():
    """Structured log and error utilities must redact secret tokens and keys."""
    from AISERVICE.migration_pack.scripts.manifest_utils import redact_sensitive_text

    sample_text = "Connecting with token 348a9b698d47c11b5a559616edc22d905b95c4fab59391bb to db password GP123!"
    redacted = redact_sensitive_text(sample_text)
    assert "348a9b698d47c11b5a559616edc22d905b95c4fab59391bb" not in redacted
    assert "GP123!" not in redacted
    assert "[REDACTED]" in redacted
