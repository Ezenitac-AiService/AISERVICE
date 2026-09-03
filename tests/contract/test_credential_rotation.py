"""Negative authentication contract for FRP and SSH credential rotation."""

from __future__ import annotations

import json

from migration_pack.scripts.credential_rotation import verify_credential_rotation


def _rotated_authenticator(current: str):
    def authenticate(candidate: str) -> bool:
        return candidate == current

    return authenticate


def test_old_frp_token_is_rejected_and_evidence_is_redacted() -> None:
    old_token = "old-frp-token-for-test"
    new_token = "new-frp-token-for-test"
    evidence = verify_credential_rotation(
        _rotated_authenticator(new_token), old_token, new_token, credential_type="frp_token"
    )
    assert evidence["old_credential_rejected"] is True
    assert evidence["new_credential_accepted"] is True
    assert evidence["rotation_verified"] is True
    encoded = json.dumps(evidence)
    assert old_token not in encoded
    assert new_token not in encoded
    assert evidence["secret_values_logged"] is False


def test_old_ssh_private_key_is_rejected_and_evidence_is_redacted() -> None:
    old_key = "old-ssh-private-key-for-test"
    new_key = "new-ssh-private-key-for-test"
    evidence = verify_credential_rotation(
        _rotated_authenticator(new_key), old_key, new_key, credential_type="ssh_private_key"
    )
    assert evidence["old_credential_rejected"] is True
    assert evidence["new_credential_accepted"] is True
    assert evidence["rotation_verified"] is True
    assert old_key not in json.dumps(evidence)
    assert new_key not in json.dumps(evidence)

