"""Unit tests for NetworkDetector active interface scanner and multi-NIC filtering.

Feature: 025-server-ip-management & 064-sample-scripts-real-ip
"""

import os
import pytest
from unittest.mock import patch, MagicMock
import src.core.network_detector as nd_mod
from src.core.network_detector import NetworkInterfaceInfo, ServerNetworkConfig, NetworkDetector
from sample.common import get_server_host


def test_network_interface_info_dataclass():
    """Verify NetworkInterfaceInfo dataclass fields."""
    info = NetworkInterfaceInfo(
        name="eth0",
        ip_address="192.168.0.80",
        is_active=True,
        is_loopback=False,
        is_usable_lan=True
    )
    assert info.name == "eth0"
    assert info.ip_address == "192.168.0.80"
    assert info.is_active is True
    assert info.is_usable_lan is True


def test_server_network_config_defaults():
    """Verify ServerNetworkConfig default values."""
    cfg = ServerNetworkConfig()
    assert cfg.bind_host == "0.0.0.0"
    assert cfg.api_port == 8081
    assert cfg.llama_server_port == 8089
    assert cfg.firewall_auto_allow is True
    assert "192.168.0.0/16" in cfg.allowed_subnets


def test_network_detector_unassigned_dual_lan_port_handling():
    """Verify that unassigned/down 2nd LAN port is safely filtered out without raising errors."""
    mock_addrs = {
        "lo": [MagicMock(family=2, address="127.0.0.1")],
        "eth0": [MagicMock(family=2, address="192.168.0.80")],
        "eth1": [MagicMock(family=2, address="0.0.0.0")]  # Unassigned second port
    }
    mock_stats = {
        "lo": MagicMock(isup=True),
        "eth0": MagicMock(isup=True),
        "eth1": MagicMock(isup=False)  # Link Down
    }

    fake_psutil = MagicMock()
    fake_psutil.net_if_addrs.return_value = mock_addrs
    fake_psutil.net_if_stats.return_value = mock_stats

    with patch.object(nd_mod, "psutil", fake_psutil):
        ifaces = NetworkDetector.scan_interfaces()
        usable_ips = [iface.ip_address for iface in ifaces if iface.is_usable_lan]
        assert "192.168.0.80" in usable_ips
        assert "127.0.0.1" not in usable_ips
        assert "0.0.0.0" not in usable_ips


def test_get_server_host_env_override():
    """Verify get_server_host prioritizes SERVER_HOST environment variable."""
    with patch.dict(os.environ, {"SERVER_HOST": "http://192.168.0.250:8081/v1"}):
        host = get_server_host()
        assert host == "http://192.168.0.250"


def test_get_server_host_platform_default():
    """Verify get_server_host falls back to platform IP default when env is unset."""
    with patch.dict(os.environ, {}, clear=True):
        host = get_server_host()
        assert host in ["http://127.0.0.1", "http://192.168.0.175", "http://192.168.0.80"]




def test_ip_subnet_guard_filtering():
    """Verify IpSubnetGuard filtering for 10.0.0.0/8 dev subnet and 192.168.0.0/16 trainee subnet."""
    from src.api.middleware.subnet_filter import IpSubnetGuard

    guard_dev = IpSubnetGuard(["127.0.0.1", "10.0.0.0/8"])
    assert guard_dev.is_allowed("10.0.1.50") is True
    assert guard_dev.is_allowed("192.168.0.50") is False

    guard_trainee = IpSubnetGuard(["127.0.0.1", "192.168.0.0/16"])
    assert guard_trainee.is_allowed("192.168.1.100") is True
    assert guard_trainee.is_allowed("10.0.1.50") is False
