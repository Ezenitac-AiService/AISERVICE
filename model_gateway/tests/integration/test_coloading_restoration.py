"""
Integration test for post-benchmark detached co-loading restoration (US3, FR-006, SC-004).
"""

import pytest
import os
from src.core.process_manager import ProcessManager
from src.core.auxiliary_manager import AuxiliaryModelManager


def test_coloading_group_config():
    """FR-006: Verify AuxiliaryModelManager is configured for embedding port 8090 and reranker port 8091."""
    aux_mgr = AuxiliaryModelManager()
    assert aux_mgr.embedding_port == 8090
    assert aux_mgr.rerank_port == 8091
    assert aux_mgr.embedding_enabled is True
    assert aux_mgr.rerank_enabled is True


def test_start_server_script_exists():
    """FR-006: Verify start_server.sh script exists for detached daemon restoration."""
    start_script = os.path.abspath("scripts/start_server.sh")
    assert os.path.exists(start_script)
    assert os.access(start_script, os.X_OK)
