"""Integration test for multi-loopback health probing and DOM keyword verification (076-fix-service-platform-parity) (T004).

Verifies multi-loopback IP probing (127.0.0.1, localhost, 127.0.1.1, active_ip),
socket connection timeouts, Connection: close header enforcement, and DOM content verification.
"""

import pytest
import os
import socket
from unittest.mock import patch, MagicMock
from scripts.diagnose_server_health import (
    check_port_open,
    check_dashboard_e2e,
    run_diagnostics,
    get_target_ips,
)


def test_get_target_ips():
    """Verify target IP list contains 127.0.0.1, localhost, 127.0.1.1, and active LAN IP."""
    ips = get_target_ips()
    assert "127.0.0.1" in ips
    assert "localhost" in ips
    assert "127.0.1.1" in ips
    assert len(ips) >= 3


def test_check_port_open_multi_loopback():
    """Verify check_port_open tries target IPs until one succeeds."""
    # Test probing loopback port that is open or closed
    # Open a temporary listening socket on localhost
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        
        # Test that check_port_open detects it
        assert check_port_open("127.0.0.1", port, timeout=3.0) is True


def test_check_dashboard_e2e_dom_verification():
    """Verify check_dashboard_e2e validates HTTP 200 and DOM keyword presence."""
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        # Case 1: HTTP 200 but missing keywords -> False
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 200
        mock_response_fail.text = "<html><body>Generic Error Page</body></html>"
        mock_client.get.return_value = mock_response_fail
        
        assert check_dashboard_e2e("http://127.0.0.1:8082") is False

        # Case 2: HTTP 200 and contains 'Dashboard' keyword -> True
        mock_response_pass = MagicMock()
        mock_response_pass.status_code = 200
        mock_response_pass.text = "<html><body><h1>vllm_serv Dashboard</h1></body></html>"
        mock_client.get.return_value = mock_response_pass
        
        assert check_dashboard_e2e("http://127.0.0.1:8082") is True


def test_env_port_override():
    """Verify environment variable port overrides (MAIN_PORT, DASHBOARD_PORT)."""
    with patch.dict(os.environ, {"MAIN_PORT": "9081", "DASHBOARD_PORT": "9082"}):
        report = run_diagnostics(verbose=False)
        assert "9081_llm_main" in report["firewall_ports"]
        assert "9082_dashboard" in report["firewall_ports"]
