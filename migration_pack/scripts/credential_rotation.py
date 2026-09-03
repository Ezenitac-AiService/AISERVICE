#!/usr/bin/env python3
"""Credential rotation checks with redacted, machine-readable evidence.

The caller owns the actual FRP/SSH authentication operation.  This module only
evaluates the old/new result pair and deliberately never serializes either
credential value.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def verify_credential_rotation(
    authenticate: Callable[[str], bool],
    old_credential: str,
    new_credential: str,
    *,
    credential_type: str,
) -> dict[str, Any]:
    """Require old rejection and new acceptance without exposing secrets."""

    old_accepted = bool(authenticate(old_credential))
    new_accepted = bool(authenticate(new_credential))
    return {
        "credential_type": credential_type,
        "old_credential_rejected": not old_accepted,
        "new_credential_accepted": new_accepted,
        "rotation_verified": (not old_accepted) and new_accepted,
        "secret_values_logged": False,
        "evidence": "redacted",
    }


def assert_rotation_verified(evidence: dict[str, Any]) -> None:
    """Raise a stable error when a rotation negative test did not pass."""

    if not evidence.get("rotation_verified"):
        raise RuntimeError("credential rotation verification failed")

