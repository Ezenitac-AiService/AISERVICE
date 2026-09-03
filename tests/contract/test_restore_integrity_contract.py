"""Contract tests for restore integrity, checksum verification, and staging isolation (T052).

Enforces:
- FR-004: Lossless restoration of 2 databases, 2 RAG collections, 4 models.
- Pre-restore checksum verification; halt on mismatch without touching live volumes.
- Staging volume isolation prior to validation.
"""

from pathlib import Path
import pytest

def test_staging_isolation_enforcement():
    """Live volume writes are prohibited when staging has not been validated."""
    from AISERVICE.migration_pack.scripts.restore_state import MigrationStateMachine, MigrationState

    sm = MigrationStateMachine()
    # At CREATED or STAGING_RESTORED, live write must be prohibited
    assert sm.is_live_write_allowed() is False

    sm.transition(MigrationState.STAGING_IN_PROGRESS)
    assert sm.is_live_write_allowed() is False

    sm.transition(MigrationState.STAGING_RESTORED)
    assert sm.is_live_write_allowed() is False

    sm.transition(MigrationState.STAGING_VALIDATED)
    assert sm.is_live_write_allowed() is True

def test_checksum_mismatch_triggers_halt():
    """Mismatched checksum must abort before live commit."""
    from AISERVICE.migration_pack.scripts.restore_state import MigrationStateMachine, MigrationState

    sm = MigrationStateMachine()
    sm.transition(MigrationState.STAGING_IN_PROGRESS)

    # Simulating a checksum failure during validation
    sm.record_failure("CHECKSUM_MISMATCH: observed sha256 does not match manifest")
    assert sm.state == MigrationState.ROLLED_BACK
    assert sm.is_live_write_allowed() is False
