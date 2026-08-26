"""
Real-execution Test Suite for FirewallManager & Network Socket Probing (FR-003, FR-004, FR-006).
Strictly obeys Constitution v1.4.0 (No Mocks, Real Socket Probes, Real OS Rule Inspection).

039-seed-pack-sudo-firewall-migration.
"""

import os
import pytest
from src.core.firewall_manager import FirewallManager, FirewallStatusInfo, RealSocketResult


def test_detect_firewall_system_real():
    """T005: Detect OS firewall utility on physical host without mocks."""
    fw_type = FirewallManager.detect_firewall_system()
    assert fw_type in FirewallManager.SUPPORTED_FIREWALL_TYPES


def test_is_port_allowed_in_os_real():
    """T005: Query actual OS firewall ruleset for port 8081."""
    is_allowed = FirewallManager.is_port_allowed_in_os(8081, "tcp")
    assert isinstance(is_allowed, bool)


def test_real_socket_connectivity_probe():
    """T005: Probe physical host TCP socket connection on port 8081."""
    result = FirewallManager.verify_real_socket_connectivity(host="127.0.0.1", port=8081, timeout_s=1.0)
    assert isinstance(result, RealSocketResult)
    assert result.target_port == 8081
    assert result.rtt_ms >= 0.0


def test_allow_port_returns_guide_message_on_sudo_restriction():
    """T009: FirewallManager returns structured guide banner when non-interactive sudo is restricted."""
    fm = FirewallManager()
    status_info = fm.allow_port(8081, "tcp")
    assert hasattr(status_info, "system_type")
    assert hasattr(status_info, "guide_message")
    assert isinstance(status_info.guide_message, str)


# ==============================================================================
# 039-seed-pack-sudo-firewall-migration (T009, T010)
# ==============================================================================

def test_firewall_manager_supported_types():
    """T009 [US2]: Verify SUPPORTED_FIREWALL_TYPES includes all multi-OS backends (ufw, firewalld, nftables, iptables, unknown)."""
    expected = {"ufw", "firewalld", "nftables", "iptables", "unknown"}
    assert set(FirewallManager.SUPPORTED_FIREWALL_TYPES) == expected


def test_detect_firewall_returns_supported_type():
    """T009 [US2]: Real OS firewall detection returns a value from SUPPORTED_FIREWALL_TYPES without mocks."""
    fw_type = FirewallManager.detect_firewall_system()
    assert fw_type in FirewallManager.SUPPORTED_FIREWALL_TYPES, \
        f"Detected type '{fw_type}' not in SUPPORTED_FIREWALL_TYPES"


def test_allow_port_returns_firewall_status_info():
    """T009 [US2]: allow_port returns FirewallStatusInfo with all required fields for any detected firewall."""
    fm = FirewallManager()
    result = fm.allow_port(8081, "tcp")
    assert isinstance(result, FirewallStatusInfo)
    assert result.system_type in FirewallManager.SUPPORTED_FIREWALL_TYPES
    assert isinstance(result.is_firewall_active, bool)
    assert isinstance(result.port_open_success, bool)
    assert isinstance(result.requires_sudo, bool)
    assert isinstance(result.guide_message, str)


def test_ensure_service_ports_open_multiple():
    """T009 [US2]: ensure_service_ports_open returns list of FirewallStatusInfo for both 8081 and 8089."""
    fm = FirewallManager()
    results = fm.ensure_service_ports_open([8081, 8089])
    assert len(results) == 2
    for r in results:
        assert isinstance(r, FirewallStatusInfo)
        assert r.system_type in FirewallManager.SUPPORTED_FIREWALL_TYPES


def test_generate_fallback_script_creates_executable(tmp_path):
    """T010 [US2]: generate_fallback_script creates an executable shell script at specified path."""
    script_path = str(tmp_path / "test_configure_firewall.sh")
    result_path = FirewallManager.generate_fallback_script(target_path=script_path, ports=[8081, 8089])

    assert os.path.exists(result_path)
    assert os.access(result_path, os.X_OK), "Generated script must be executable"

    with open(result_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "#!/usr/bin/env bash" in content
    assert "8081" in content
    assert "8089" in content
    assert "EUID" in content


def test_generate_fallback_script_skips_existing(tmp_path):
    """T010 [US2]: generate_fallback_script preserves existing script (non-destructive)."""
    script_path = str(tmp_path / "existing_firewall.sh")
    with open(script_path, "w") as f:
        f.write("#!/bin/bash\n# existing content\n")

    result_path = FirewallManager.generate_fallback_script(target_path=script_path)
    with open(result_path, "r") as f:
        content = f.read()

    assert "existing content" in content, "Existing script must not be overwritten"

