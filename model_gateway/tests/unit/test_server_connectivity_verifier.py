"""Unit tests for ServerConnectivityVerifier module.

Feature: 034-assigned-ip-server-test
"""

import socket
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from src.core.server_connectivity_verifier import (
    ServerConnectivityVerifier,
    IPTestVerdict,
    ConnectivityReport,
    ServerNetworkContext
)


def test_dataclasses():
    """Tests dataclass initialization and field defaults."""
    verdict = IPTestVerdict(
        ip_address="127.0.0.1",
        port=8081,
        endpoint="/health",
        status="SUCCESS",
        http_status_code=200,
        response_time_ms=12.5
    )
    assert verdict.ip_address == "127.0.0.1"
    assert verdict.status == "SUCCESS"
    assert verdict.http_status_code == 200

    report = ConnectivityReport(
        tested_ips=["127.0.0.1", "192.168.1.10"],
        verdicts=[verdict],
        all_passed=True,
        summary_message="All PASSED"
    )
    assert len(report.tested_ips) == 2
    assert report.all_passed is True

    context = ServerNetworkContext()
    assert context.bind_host == "0.0.0.0"
    assert context.api_port == 8081
    assert context.loopback_ip == "127.0.0.1"


def test_get_target_ips_dual_lan():
    """Tests get_target_ips() collects 127.0.0.1 and all active dual LAN IPs without duplicates."""
    verifier = ServerConnectivityVerifier(port=8081)

    with patch("src.core.server_connectivity_verifier.NetworkDetector.get_active_lan_ips") as mock_lan:
        mock_lan.return_value = ["192.168.1.100", "10.0.0.5", "127.0.0.1"]
        target_ips = verifier.get_target_ips()

        assert target_ips == ["127.0.0.1", "192.168.1.100", "10.0.0.5"]
        assert len(target_ips) == 3


def test_verify_ip_success():
    """Tests verify_ip() when HTTP GET returns 200 OK."""
    verifier = ServerConnectivityVerifier(port=8081, endpoint="/health", timeout=2.0)

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        verdict = verifier.verify_ip("192.168.1.100")

        assert verdict.ip_address == "192.168.1.100"
        assert verdict.status == "SUCCESS"
        assert verdict.http_status_code == 200
        assert verdict.response_time_ms >= 0.0
        assert verdict.error_message is None


def test_verify_ip_connection_refused():
    """Tests verify_ip() when connection is refused by target IP."""
    verifier = ServerConnectivityVerifier(port=8081, endpoint="/health", timeout=2.0)

    err = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
    with patch("urllib.request.urlopen", side_effect=err):
        verdict = verifier.verify_ip("192.168.1.100")

        assert verdict.ip_address == "192.168.1.100"
        assert verdict.status == "CONNECTION_REFUSED"
        assert "Connection refused" in verdict.error_message


def test_verify_ip_timeout():
    """Tests verify_ip() when request times out."""
    verifier = ServerConnectivityVerifier(port=8081, endpoint="/health", timeout=1.0)

    err = socket.timeout("timed out")
    with patch("urllib.request.urlopen", side_effect=err):
        verdict = verifier.verify_ip("10.0.0.5")

        assert verdict.ip_address == "10.0.0.5"
        assert verdict.status == "TIMEOUT"
        assert "timed out" in verdict.error_message.lower()


def test_verify_all_aggregation():
    """Tests verify_all() aggregates pass/fail verdicts into a ConnectivityReport."""
    verifier = ServerConnectivityVerifier(port=8081)

    v_pass = IPTestVerdict(ip_address="127.0.0.1", port=8081, endpoint="/health", status="SUCCESS", http_status_code=200)
    v_fail = IPTestVerdict(ip_address="192.168.1.100", port=8081, endpoint="/health", status="CONNECTION_REFUSED", error_message="Refused")

    with patch.object(verifier, "get_target_ips", return_value=["127.0.0.1", "192.168.1.100"]):
        with patch.object(verifier, "verify_ip", side_effect=[v_pass, v_fail]):
            report = verifier.verify_all()

            assert report.all_passed is False
            assert report.failed_ips == ["192.168.1.100"]
            assert len(report.verdicts) == 2
            assert "1/2 target IP(s) PASSED" in report.summary_message
