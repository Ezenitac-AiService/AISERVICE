"""OS Firewall management, real socket probing, and port configuration utility.

Provides non-mocked OS kernel firewall status detection (ufw/firewalld/nftables/iptables)
and physical TCP socket connectivity probing.

039-seed-pack-sudo-firewall-migration (FR-003, FR-004, FR-006).
"""

import os
import stat
import time
import socket
import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FirewallStatusInfo:
    """Represents OS firewall status and port allow attempt results."""
    system_type: str  # ufw, firewalld, nftables, iptables, unknown
    is_firewall_active: bool
    port_open_success: bool
    requires_sudo: bool
    guide_message: str


@dataclass
class RealSocketResult:
    """Represents real physical TCP socket connectivity probe result."""
    target_host: str
    target_port: int
    socket_connected: bool
    rtt_ms: float
    error_detail: Optional[str] = None


class FirewallManager:
    """Attempts to allow service ports (8081, 8089) via ufw/firewalld/nftables/iptables and checks real OS firewall & physical TCP socket status."""

    SUPPORTED_FIREWALL_TYPES = ["ufw", "firewalld", "nftables", "iptables", "unknown"]

    @staticmethod
    def detect_firewall_system() -> str:
        """Detects available and active OS firewall management utility.

        Detection priority: ufw > firewalld > nftables > iptables > unknown.
        Checks binary availability via shutil.which AND active state where possible.
        """
        # 1. ufw (Ubuntu/Debian)
        if shutil.which("ufw"):
            try:
                res = subprocess.run(
                    ["ufw", "status"],
                    capture_output=True, text=True, timeout=5
                )
                if "Status: active" in res.stdout:
                    return "ufw"
                if res.returncode != 0:
                    res = subprocess.run(
                        ["sudo", "-n", "ufw", "status"],
                        capture_output=True, text=True, timeout=5
                    )
                    if "Status: active" in res.stdout:
                        return "ufw"
                # Default to ufw if binary is present on Debian/Ubuntu system even if non-root
                return "ufw"
            except Exception:
                return "ufw"
        # 2. firewalld (RHEL/CentOS/Rocky/Fedora)
        if shutil.which("firewall-cmd"):
            try:
                res = subprocess.run(
                    ["firewall-cmd", "--state"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0 and "running" in res.stdout.strip():
                    return "firewalld"
                res = subprocess.run(
                    ["sudo", "-n", "firewall-cmd", "--state"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0 and "running" in res.stdout.strip():
                    return "firewalld"
                return "firewalld"
            except Exception:
                return "firewalld"
        # 3. nftables (modern kernel)
        if shutil.which("nft"):
            try:
                res = subprocess.run(
                    ["nft", "list", "ruleset"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0:
                    return "nftables"
            except Exception:
                pass
        # 4. iptables (legacy)
        if shutil.which("iptables"):
            return "iptables"
        return "unknown"

    @staticmethod
    def is_port_allowed_in_os(port: int, protocol: str = "tcp") -> bool:
        """
        Non-mocked OS firewall status detector (FR-006).
        Parses actual ufw/firewalld/nftables/iptables output to check if port rule exists.
        """
        fw_type = FirewallManager.detect_firewall_system()
        try:
            if fw_type == "ufw":
                res = subprocess.run(
                    ["ufw", "status"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode != 0:
                    res = subprocess.run(
                        ["sudo", "-n", "ufw", "status"],
                        capture_output=True, text=True, timeout=5
                    )
                if "Status: active" in res.stdout:
                    target_token = f"{port}/{protocol}"
                    for line in res.stdout.splitlines():
                        if target_token in line and "ALLOW" in line.upper():
                            return True
                    return False
                return True
            elif fw_type == "firewalld":
                res = subprocess.run(
                    ["firewall-cmd", "--list-ports"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0:
                    return f"{port}/{protocol}" in res.stdout
                return True
            elif fw_type == "nftables":
                res = subprocess.run(
                    ["nft", "list", "ruleset"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0:
                    return str(port) in res.stdout
                return True
            elif fw_type == "iptables":
                res = subprocess.run(
                    ["iptables", "-C", "INPUT", "-p", protocol, "--dport", str(port), "-j", "ACCEPT"],
                    capture_output=True, text=True, timeout=5
                )
                return res.returncode == 0
        except Exception:
            pass
        return True

    @staticmethod
    def verify_real_socket_connectivity(host: str = "10.0.0.41", port: int = 8081, timeout_s: float = 3.0) -> RealSocketResult:
        """
        Real physical TCP socket connectivity probe helper (FR-006).
        Strictly prohibits in-memory mocks and performs actual socket handshake.
        """
        start_time = time.perf_counter()
        try:
            sock = socket.create_connection((host, port), timeout=timeout_s)
            sock.close()
            rtt_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return RealSocketResult(
                target_host=host,
                target_port=port,
                socket_connected=True,
                rtt_ms=rtt_ms,
                error_detail=None
            )
        except Exception as exc:
            rtt_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return RealSocketResult(
                target_host=host,
                target_port=port,
                socket_connected=False,
                rtt_ms=rtt_ms,
                error_detail=str(exc)
            )

    def _build_sudo_guide(self, fw_type: str, port: int, protocol: str) -> str:
        """Build a standardized sudo-required warning guide message."""
        commands = {
            "ufw": f"sudo ufw allow {port}/{protocol}",
            "firewalld": f"sudo firewall-cmd --permanent --add-port={port}/{protocol} && sudo firewall-cmd --reload",
            "nftables": f"sudo nft add rule inet filter input tcp dport {port} accept",
            "iptables": f"sudo iptables -A INPUT -p tcp --dport {port} -j ACCEPT",
        }
        cmd = commands.get(fw_type, f"OS 방화벽에서 포트 {port}/{protocol}을(를) 수동으로 개방하세요.")
        return (
            f"\n========================================================================\n"
            f"⚠️ OS 방화벽({fw_type}) 포트 개방 권한 거부 안내\n"
            f"------------------------------------------------------------------------\n"
            f"서버 계정의 sudo 비밀번호 권한이 필요합니다.\n"
            f"동일 내부망(10.0.0.x)에서 대시보드 및 LLM API를 수신하려면 아래 명령을 실행해 주세요:\n"
            f"\n"
            f"    {cmd}\n"
            f"========================================================================\n"
        )

    def allow_port(self, port: int, protocol: str = "tcp") -> FirewallStatusInfo:
        """Attempts to allow specified port in OS firewall (ufw/firewalld/nftables/iptables)."""
        fw_type = self.detect_firewall_system()

        if fw_type == "ufw":
            return self._allow_port_ufw(port, protocol)
        elif fw_type == "firewalld":
            return self._allow_port_firewalld(port, protocol)
        elif fw_type == "nftables":
            return self._allow_port_nftables(port, protocol)
        elif fw_type == "iptables":
            return self._allow_port_iptables(port, protocol)

        guide = f"⚠️ 서버 서비스 포트({port}/{protocol}) 접속을 허용하려면 OS 방화벽 설정을 확인해 주세요."
        return FirewallStatusInfo(
            system_type=fw_type,
            is_firewall_active=False,
            port_open_success=True,
            requires_sudo=False,
            guide_message=guide
        )

    def _allow_port_ufw(self, port: int, protocol: str) -> FirewallStatusInfo:
        """Allow port via ufw."""
        try:
            res = subprocess.run(
                ["ufw", "allow", f"{port}/{protocol}"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0:
                logger.info(f"[FirewallManager] Successfully allowed port {port}/{protocol} via ufw")
                return FirewallStatusInfo(
                    system_type="ufw",
                    is_firewall_active=True,
                    port_open_success=True,
                    requires_sudo=False,
                    guide_message=f"Port {port}/{protocol} successfully allowed via ufw"
                )
        except Exception as e:
            logger.warning(f"[FirewallManager] ufw allow exception: {e}")
        guide = self._build_sudo_guide("ufw", port, protocol)
        return FirewallStatusInfo(
            system_type="ufw", is_firewall_active=True,
            port_open_success=False, requires_sudo=True, guide_message=guide
        )

    def _allow_port_firewalld(self, port: int, protocol: str) -> FirewallStatusInfo:
        """Allow port via firewalld."""
        try:
            res = subprocess.run(
                ["firewall-cmd", "--permanent", f"--add-port={port}/{protocol}"],
                capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0:
                subprocess.run(["firewall-cmd", "--reload"], capture_output=True, timeout=10)
                logger.info(f"[FirewallManager] Successfully allowed port {port}/{protocol} via firewalld")
                return FirewallStatusInfo(
                    system_type="firewalld",
                    is_firewall_active=True,
                    port_open_success=True,
                    requires_sudo=False,
                    guide_message=f"Port {port}/{protocol} successfully allowed via firewalld"
                )
        except Exception as e:
            logger.warning(f"[FirewallManager] firewalld allow exception: {e}")
        guide = self._build_sudo_guide("firewalld", port, protocol)
        return FirewallStatusInfo(
            system_type="firewalld", is_firewall_active=True,
            port_open_success=False, requires_sudo=True, guide_message=guide
        )

    def _allow_port_nftables(self, port: int, protocol: str) -> FirewallStatusInfo:
        """Allow port via nftables."""
        try:
            res = subprocess.run(
                ["nft", "add", "rule", "inet", "filter", "input", "tcp", "dport", str(port), "accept"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0:
                logger.info(f"[FirewallManager] Successfully allowed port {port}/{protocol} via nftables")
                return FirewallStatusInfo(
                    system_type="nftables",
                    is_firewall_active=True,
                    port_open_success=True,
                    requires_sudo=False,
                    guide_message=f"Port {port}/{protocol} successfully allowed via nftables"
                )
        except Exception as e:
            logger.warning(f"[FirewallManager] nftables allow exception: {e}")
        guide = self._build_sudo_guide("nftables", port, protocol)
        return FirewallStatusInfo(
            system_type="nftables", is_firewall_active=True,
            port_open_success=False, requires_sudo=True, guide_message=guide
        )

    def _allow_port_iptables(self, port: int, protocol: str) -> FirewallStatusInfo:
        """Allow port via iptables."""
        try:
            check = subprocess.run(
                ["iptables", "-C", "INPUT", "-p", protocol, "--dport", str(port), "-j", "ACCEPT"],
                capture_output=True, text=True, timeout=5
            )
            if check.returncode == 0:
                logger.info(f"[FirewallManager] Port {port}/{protocol} already allowed via iptables")
                return FirewallStatusInfo(
                    system_type="iptables",
                    is_firewall_active=True,
                    port_open_success=True,
                    requires_sudo=False,
                    guide_message=f"Port {port}/{protocol} already allowed via iptables"
                )
            res = subprocess.run(
                ["iptables", "-A", "INPUT", "-p", protocol, "--dport", str(port), "-j", "ACCEPT"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0:
                logger.info(f"[FirewallManager] Successfully allowed port {port}/{protocol} via iptables")
                return FirewallStatusInfo(
                    system_type="iptables",
                    is_firewall_active=True,
                    port_open_success=True,
                    requires_sudo=False,
                    guide_message=f"Port {port}/{protocol} successfully allowed via iptables"
                )
        except Exception as e:
            logger.warning(f"[FirewallManager] iptables allow exception: {e}")
        guide = self._build_sudo_guide("iptables", port, protocol)
        return FirewallStatusInfo(
            system_type="iptables", is_firewall_active=True,
            port_open_success=False, requires_sudo=True, guide_message=guide
        )

    def ensure_service_ports_open(self, ports: List[int]) -> List[FirewallStatusInfo]:
        """Attempts to allow a list of service ports."""
        results = []
        for port in ports:
            results.append(self.allow_port(port))
        return results

    @staticmethod
    def generate_fallback_script(target_path: str = "scripts/configure_firewall.sh",
                                  ports: Optional[List[int]] = None) -> str:
        """Generates executable standalone helper shell script for manual/sudo execution (FR-004).

        Returns absolute path to generated script.
        """
        if ports is None:
            ports = [8081, 8089]

        abs_path = os.path.abspath(target_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        # If the script already exists (e.g., packaged via seed pack), keep it.
        if os.path.exists(abs_path):
            logger.info(f"[FirewallManager] Fallback script already exists at {abs_path}")
            return abs_path

        port_args = " ".join(str(p) for p in ports)
        script_content = f"""#!/usr/bin/env bash
# Auto-generated by vllm_serv setup.sh (039-seed-pack-sudo-firewall-migration)
# Usage: sudo {target_path} [{port_args}]
set -eo pipefail
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: root 권한이 필요합니다. sudo $0 을(를) 사용하세요."
    exit 1
fi
TARGET_PORTS=({port_args})
if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -qi 'active'; then
    for p in "${{TARGET_PORTS[@]}}"; do ufw allow "$p/tcp"; done
elif command -v firewall-cmd &>/dev/null && firewall-cmd --state 2>/dev/null | grep -qi 'running'; then
    for p in "${{TARGET_PORTS[@]}}"; do firewall-cmd --permanent --add-port="$p/tcp"; done
    firewall-cmd --reload
elif command -v nft &>/dev/null; then
    for p in "${{TARGET_PORTS[@]}}"; do nft add rule inet filter input tcp dport "$p" accept 2>/dev/null || true; done
elif command -v iptables &>/dev/null; then
    for p in "${{TARGET_PORTS[@]}}"; do iptables -C INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport "$p" -j ACCEPT; done
else
    echo "WARN: 활성화된 방화벽을 감지할 수 없습니다."
fi
echo "방화벽 포트 구성 완료: ${{TARGET_PORTS[*]}}"
"""
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        os.chmod(abs_path, os.stat(abs_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        logger.info(f"[FirewallManager] Generated fallback script at {abs_path}")
        return abs_path
