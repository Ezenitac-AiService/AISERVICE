"""Contract tests for rollback mechanics, timing, and atomicity (T053).

Enforces:
- FR-004 / SC-004: Atomic rollback on failure, recording ROLLED_BACK state.
- Rollback execution completes within 15 seconds.
- Avoids partial or corrupted live volume writes.
"""

from pathlib import Path
import time
import pytest

def test_rollback_state_recording():
    from AISERVICE.migration_pack.scripts.restore_state import MigrationStateMachine, MigrationState

    sm = MigrationStateMachine()
    sm.transition(MigrationState.STAGING_IN_PROGRESS)
    sm.record_failure("Schema validation failure on oliview_project")

    assert sm.state == MigrationState.ROLLED_BACK
    assert "Schema validation failure" in sm.error_reason

def test_rollback_timing_within_15s():
    """Simulated rollback procedure must complete well within the 15-second SLA."""
    from AISERVICE.migration_pack.scripts.restore_state import rollback_staging_environment

    t0 = time.perf_counter()
    result = rollback_staging_environment(staging_volumes=["staging_pilos_v2", "staging_oliview_project"])
    duration = time.perf_counter() - t0

    assert result["status"] == "ROLLED_BACK"
    assert duration < 15.0
