"""Unit tests for FirewallManager OS firewall auto-allow attempt and exception handling.

Feature: 025-server-ip-management
"""

import pytest
from unittest.mock import patch, MagicMock
from src.core.firewall_manager import FirewallManager, FirewallStatusInfo


def test_firewall_status_info_dataclass():
    """Verify FirewallStatusInfo structure."""
    info = FirewallStatusInfo(
        system_type="ufw",
        is_firewall_active=True,
        port_open_success=True,
        requires_sudo=False,
        guide_message=""
    )
    assert info.system_type == "ufw"
    assert info.port_open_success is True


def test_firewall_manager_graceful_permission_denied():
    """Verify FirewallManager logs warning and returns requires_sudo=True when firewall requires sudo."""
    fm = FirewallManager()
    with patch.object(FirewallManager, "detect_firewall_system", return_value="ufw"):
        with patch("subprocess.run") as mock_run:
            # Simulate ufw requiring sudo / failing with returncode 1
            mock_run.return_value = MagicMock(returncode=1, stderr="Permission denied (you must be root)")
            status = fm.allow_port(8081)
            assert status.requires_sudo is True
            assert "sudo ufw allow 8081/tcp" in status.guide_message


def test_ufw_sudo_fallback_detection():
    """Verify detect_firewall_system detects ufw via sudo -n when unprivileged ufw status fails (FR-003)."""
    with patch("shutil.which", side_effect=lambda cmd: "/usr/sbin/ufw" if cmd == "ufw" else None):
        with patch("subprocess.run") as mock_run:
            # First call (unprivileged ufw status) returns code 1
            # Second call (sudo -n ufw status) returns Status: active
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="you must be root"),
                MagicMock(returncode=0, stdout="Status: active\n", stderr="")
            ]
            fw_type = FirewallManager.detect_firewall_system()
            assert fw_type == "ufw"

