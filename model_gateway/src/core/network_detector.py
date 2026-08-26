"""Network interface detection and active IP scanning utility for multi-NIC environments.

Feature: 025-server-ip-management & 064-sample-scripts-real-ip
"""

import os
import socket
import logging
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)


@dataclass
class NetworkInterfaceInfo:
    """Represents a physical or logical network interface card (NIC)."""
    name: str
    ip_address: Optional[str]
    is_active: bool
    is_loopback: bool
    is_usable_lan: bool


@dataclass
class ServerNetworkConfig:
    """Server network configuration and binding specification."""
    bind_host: str = "0.0.0.0"
    api_port: int = 8081
    llama_server_port: int = 8089
    allowed_subnets: List[str] = field(default_factory=lambda: [
        "127.0.0.1",
        "192.168.0.0/16",
        "10.0.0.0/8",
        "172.16.0.0/12"
    ])
    detected_active_ips: List[str] = field(default_factory=list)
    firewall_auto_allow: bool = True


class NetworkDetector:
    """Detects physical/logical network interfaces, filters unassigned/down ports, and extracts active LAN IPv4 addresses."""

    @staticmethod
    def scan_interfaces() -> List[NetworkInterfaceInfo]:
        """Scans system network interfaces and returns list of NetworkInterfaceInfo."""
        interfaces: List[NetworkInterfaceInfo] = []

        if psutil is not None:
            try:
                stats = psutil.net_if_stats()
                addrs = psutil.net_if_addrs()

                for iface_name, addr_list in addrs.items():
                    stat = stats.get(iface_name)
                    is_active = stat.isup if stat else True

                    for addr in addr_list:
                        if addr.family == socket.AF_INET:
                            ip = addr.address
                            is_loopback = (ip.startswith("127.") or iface_name.startswith("lo"))
                            is_usable = (
                                is_active and
                                not is_loopback and
                                bool(ip) and
                                ip != "0.0.0.0" and
                                not ip.startswith("169.254.")  # Skip APIPA / link-local
                            )
                            interfaces.append(NetworkInterfaceInfo(
                                name=iface_name,
                                ip_address=ip,
                                is_active=is_active,
                                is_loopback=is_loopback,
                                is_usable_lan=is_usable
                            ))
            except Exception as e:
                logger.warning(f"[NetworkDetector] psutil interface scan failed: {e}")

        # Fallback to standard socket if psutil is unavailable or returned empty list
        if not interfaces:
            try:
                hostname = socket.gethostname()
                addr_info = socket.gethostbyname_ex(hostname)
                for ip in addr_info[2]:
                    is_loopback = ip.startswith("127.")
                    is_usable = not is_loopback and not ip.startswith("169.254.")
                    interfaces.append(NetworkInterfaceInfo(
                        name="primary",
                        ip_address=ip,
                        is_active=True,
                        is_loopback=is_loopback,
                        is_usable_lan=is_usable
                    ))
            except Exception as e:
                logger.warning(f"[NetworkDetector] socket interface scan fallback failed: {e}")

        # Secondary fallback: UDP routing socket check if no usable LAN IP found yet
        usable_found = any(iface.is_usable_lan for iface in interfaces)
        if not usable_found:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("10.255.255.255", 1))
                ip = s.getsockname()[0]
                s.close()
                if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                    interfaces.append(NetworkInterfaceInfo(
                        name="udp_route",
                        ip_address=ip,
                        is_active=True,
                        is_loopback=False,
                        is_usable_lan=True
                    ))
            except Exception as e:
                logger.warning(f"[NetworkDetector] UDP route interface scan fallback failed: {e}")

        return interfaces

    @classmethod
    def get_active_lan_ips(cls) -> List[str]:
        """Returns list of active IPv4 LAN addresses (excluding loopback and unassigned interfaces)."""
        active_ips: List[str] = []
        for iface in cls.scan_interfaces():
            if iface.is_usable_lan and iface.ip_address and iface.ip_address not in active_ips:
                active_ips.append(iface.ip_address)
        return active_ips

    @classmethod
    def get_server_network_config(
        cls,
        bind_host: str = "0.0.0.0",
        api_port: int = 8081,
        llama_server_port: int = 8089,
        firewall_auto_allow: bool = True
    ) -> ServerNetworkConfig:
        """Constructs ServerNetworkConfig with active LAN IPs populated."""
        active_ips = cls.get_active_lan_ips()
        return ServerNetworkConfig(
            bind_host=bind_host,
            api_port=api_port,
            llama_server_port=llama_server_port,
            detected_active_ips=active_ips,
            firewall_auto_allow=firewall_auto_allow
        )
