import os
import pytest

def pytest_addoption(parser):
    parser.addoption(
        "--real",
        action="store_true",
        default=False,
        help="Run tests in Real GPU Execution Mode (spawning real llama-server subprocesses)"
    )
    parser.addoption(
        "--real-network",
        action="store_true",
        default=False,
        help="Run tests in Real Network & OS Firewall Verification Mode (physical host IP)"
    )

@pytest.fixture(autouse=True, scope="session")
def setup_mock_llama_server_default(request):
    is_real = request.config.getoption("--real") or os.environ.get("TEST_MODE") == "real"
    if not is_real and "MOCK_LLAMA_SERVER" not in os.environ:
        os.environ["MOCK_LLAMA_SERVER"] = "1"

@pytest.fixture
def test_mode(request):
    is_real = request.config.getoption("--real") or os.environ.get("TEST_MODE") == "real"
    return "real" if is_real else "mock"


@pytest.fixture
def is_real_network(request):
    return request.config.getoption("--real-network") or os.environ.get("REAL_NETWORK_TEST") == "1"

@pytest.fixture(scope="session")
def target_host_ip():
    env_ip = os.environ.get("HOST_IP")
    if env_ip:
        return env_ip
    try:
        from src.core.network_detector import NetworkDetector
        active_ips = NetworkDetector.get_active_lan_ips()
        if active_ips:
            return active_ips[0]
    except Exception:
        pass
    return "10.0.0.41"

@pytest.fixture(scope="session")
def base_url(target_host_ip):
    return f"http://{target_host_ip}:8081"


