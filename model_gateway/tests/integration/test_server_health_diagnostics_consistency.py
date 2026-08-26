import subprocess
import pytest
from scripts.diagnose_server_health import check_port_open, check_dashboard_e2e, get_target_ips

def test_status_server_script_vs_python_diagnostics_consistency():
    """T003/SC-001: Verifies status_server.sh output matches diagnose_server_health.py."""
    target_ips = get_target_ips()
    
    # 1. Test port 8082 open via diagnose_server_health
    port_8082_open = check_port_open(target_ips, 8082)
    dash_e2e_ok = check_dashboard_e2e([f"http://{ip}:8082/" for ip in target_ips])
    
    # 2. Run status_server.sh script
    res = subprocess.run(["./status_server.sh"], capture_output=True, text=True)
    assert res.returncode == 0
    stdout = res.stdout
    
    if port_8082_open and dash_e2e_ok:
        assert "Port 8082 OPEN" in stdout
        assert "Port 8082 CLOSED" not in stdout
