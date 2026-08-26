from src.api.middleware.subnet_filter import IpSubnetGuard

def test_ip_subnet_guard_allowed():
    guard = IpSubnetGuard(["127.0.0.1", "192.168.0.0/24"])
    assert guard.is_allowed("127.0.0.1") is True
    assert guard.is_allowed("192.168.0.1") is True
    assert guard.is_allowed("192.168.0.100") is True
    assert guard.is_allowed("testclient") is True

def test_ip_subnet_guard_forbidden():
    guard = IpSubnetGuard(["127.0.0.1", "192.168.0.0/24"])
    assert guard.is_allowed("10.0.0.1") is False
    assert guard.is_allowed("203.0.113.5") is False
    assert guard.is_allowed("1.1.1.1") is False
