"""Server connectivity and assigned IP response verifier module.

Feature: 034-assigned-ip-server-test
"""

import time
import socket
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Optional

from src.core.network_detector import NetworkDetector

logger = logging.getLogger(__name__)


@dataclass
class IPTestVerdict:
    """Detailed verification result for a single IP address and port."""
    ip_address: str
    port: int
    endpoint: str
    status: str  # "SUCCESS", "FAILED", "TIMEOUT", "CONNECTION_REFUSED"
    http_status_code: Optional[int] = None
    response_time_ms: float = 0.0
    error_message: Optional[str] = None


@dataclass
class ConnectivityReport:
    """Aggregated network connectivity report for all target IPs."""
    tested_ips: List[str] = field(default_factory=list)
    verdicts: List[IPTestVerdict] = field(default_factory=list)
    all_passed: bool = False
    failed_ips: List[str] = field(default_factory=list)
    summary_message: str = ""


@dataclass
class ServerNetworkContext:
    """Context holding server binding and target IP information."""
    bind_host: str = "0.0.0.0"
    api_port: int = 8081
    loopback_ip: str = "127.0.0.1"
    active_lan_ips: List[str] = field(default_factory=list)


class ServerConnectivityVerifier:
    """Verifies HTTP service responsiveness across loopback and all assigned host IP addresses."""

    def __init__(self, port: int = 8081, endpoint: str = "/health", timeout: float = 3.0):
        """Initializes verifier with target port, endpoint path, and request timeout."""
        self.port = port
        self.endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        self.timeout = timeout

    def get_target_ips(self) -> List[str]:
        """Returns loopback IP ('127.0.0.1') and all active non-loopback LAN IPs (dual LAN)."""
        target_ips = ["127.0.0.1"]
        try:
            lan_ips = NetworkDetector.get_active_lan_ips()
            for ip in lan_ips:
                if ip not in target_ips:
                    target_ips.append(ip)
        except Exception as e:
            logger.warning(f"[ServerConnectivityVerifier] Failed to scan active LAN IPs: {e}")
        return target_ips

    def verify_ip(self, ip_address: str) -> IPTestVerdict:
        """Attempts HTTP GET connection to target IP address and endpoint.

        Returns:
            IPTestVerdict containing status, response_time_ms, http_status_code, and error_message.
        """
        url = f"http://{ip_address}:{self.port}{self.endpoint}"
        start_time = time.perf_counter()

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vllm-serv-verifier/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                status_code = resp.getcode()
                if 200 <= status_code < 400:
                    return IPTestVerdict(
                        ip_address=ip_address,
                        port=self.port,
                        endpoint=self.endpoint,
                        status="SUCCESS",
                        http_status_code=status_code,
                        response_time_ms=round(elapsed_ms, 2)
                    )
                else:
                    return IPTestVerdict(
                        ip_address=ip_address,
                        port=self.port,
                        endpoint=self.endpoint,
                        status="FAILED",
                        http_status_code=status_code,
                        response_time_ms=round(elapsed_ms, 2),
                        error_message=f"HTTP Status {status_code}"
                    )
        except urllib.error.HTTPError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return IPTestVerdict(
                ip_address=ip_address,
                port=self.port,
                endpoint=self.endpoint,
                status="FAILED",
                http_status_code=e.code,
                response_time_ms=round(elapsed_ms, 2),
                error_message=f"HTTPError {e.code}: {e.reason}"
            )
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionRefusedError, OSError) as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            err_str = str(e)
            if "Connection refused" in err_str or isinstance(e, ConnectionRefusedError):
                status_type = "CONNECTION_REFUSED"
                msg = f"Connection refused on {ip_address}:{self.port}. Server may not be listening on 0.0.0.0 or this IP."
            elif "timed out" in err_str.lower() or isinstance(e, (socket.timeout, TimeoutError)):
                status_type = "TIMEOUT"
                msg = f"Connection timed out after {self.timeout}s on {ip_address}:{self.port}."
            else:
                status_type = "FAILED"
                msg = f"Network error on {ip_address}:{self.port}: {e}"

            return IPTestVerdict(
                ip_address=ip_address,
                port=self.port,
                endpoint=self.endpoint,
                status=status_type,
                response_time_ms=round(elapsed_ms, 2),
                error_message=msg
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return IPTestVerdict(
                ip_address=ip_address,
                port=self.port,
                endpoint=self.endpoint,
                status="FAILED",
                response_time_ms=round(elapsed_ms, 2),
                error_message=f"Unexpected error: {e}"
            )

    def verify_all(self) -> ConnectivityReport:
        """Executes verification across all target IPs and returns aggregated ConnectivityReport."""
        target_ips = self.get_target_ips()
        verdicts: List[IPTestVerdict] = []
        failed_ips: List[str] = []

        for ip in target_ips:
            verdict = self.verify_ip(ip)
            verdicts.append(verdict)
            if verdict.status != "SUCCESS":
                failed_ips.append(ip)

        all_passed = len(failed_ips) == 0
        passed_count = len(target_ips) - len(failed_ips)

        if all_passed:
            summary = f"All {len(target_ips)} target IP(s) PASSED connectivity check ({', '.join(target_ips)})."
        else:
            summary = f"{passed_count}/{len(target_ips)} target IP(s) PASSED. Failed IP(s): {', '.join(failed_ips)}."

        return ConnectivityReport(
            tested_ips=target_ips,
            verdicts=verdicts,
            all_passed=all_passed,
            failed_ips=failed_ips,
            summary_message=summary
        )
