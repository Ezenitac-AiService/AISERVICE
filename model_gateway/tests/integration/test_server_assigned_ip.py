"""Integration test for Assigned IP Server Verification.

Feature: 034-assigned-ip-server-test
"""

import time
import socket
import threading
import http.server
import pytest

from src.core.server_connectivity_verifier import ServerConnectivityVerifier
from src.core.network_detector import NetworkDetector


class HealthCheckHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Simple HTTP request handler returning 200 OK for /health endpoint."""

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "message": "server is running"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress standard HTTP logging output during tests
        pass


def find_free_port() -> int:
    """Finds a free TCP port on 0.0.0.0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mock_running_server():
    """Fixture that spins up an HTTP server listening on 0.0.0.0 in a background thread."""
    port = find_free_port()
    server = http.server.HTTPServer(("0.0.0.0", port), HealthCheckHTTPHandler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)  # Allow thread to bind & listen

    yield port

    server.shutdown()
    server.server_close()


def test_server_assigned_ip_connectivity(mock_running_server):
    """Verifies that localhost (127.0.0.1) and all assigned LAN IPs connect and respond HTTP 200 OK."""
    port = mock_running_server
    verifier = ServerConnectivityVerifier(port=port, endpoint="/health", timeout=3.0)

    target_ips = verifier.get_target_ips()
    assert "127.0.0.1" in target_ips

    report = verifier.verify_all()

    assert report.all_passed is True, f"Server connectivity failed: {report.summary_message}"
    assert len(report.failed_ips) == 0

    for verdict in report.verdicts:
        assert verdict.status == "SUCCESS"
        assert verdict.http_status_code == 200
        assert verdict.response_time_ms >= 0.0


def test_server_unreachable_ip_diagnostics():
    """Verifies diagnostic error reporting when attempting to connect to an unopened port."""
    unused_port = find_free_port()
    verifier = ServerConnectivityVerifier(port=unused_port, endpoint="/health", timeout=1.0)

    verdict = verifier.verify_ip("127.0.0.1")

    assert verdict.status in ("CONNECTION_REFUSED", "TIMEOUT", "FAILED")
    assert verdict.error_message is not None
    assert ("Connection refused" in verdict.error_message or "timed out" in verdict.error_message.lower() or "Refused" in verdict.error_message)
