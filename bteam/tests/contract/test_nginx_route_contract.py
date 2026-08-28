import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC_042 = ROOT.parent / "specs" / "042-bteam-production-cutover"
DEPLOY_NGINX = ROOT / "deployment" / "nginx"


def test_nginx_route_contract_schema():
    schema = json.loads(
        (SPEC_042 / "contracts" / "nginx_route_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert "routes" in schema["required"]
    assert "proxy_retry_policy" in schema["required"]
    assert schema["properties"]["proxy_retry_policy"]["properties"]["tries"]["minimum"] == 3


def test_candidate_conf_has_green_ports_and_retry_policy():
    conf_path = DEPLOY_NGINX / "bteam.candidate.conf"
    assert conf_path.exists(), "bteam.candidate.conf 파일이 존재해야 합니다."
    content = conf_path.read_text(encoding="utf-8")

    # Green ports
    assert "server 127.0.0.1:15050;" in content
    assert "server 127.0.0.1:15173;" in content
    assert "server 127.0.0.1:18501;" in content
    assert "server 127.0.0.1:18002;" in content

    # Retry policy
    assert "proxy_next_upstream error timeout http_502 http_503;" in content
    assert "proxy_next_upstream_tries 3;" in content


def test_rollback_conf_has_blue_ports():
    conf_path = DEPLOY_NGINX / "bteam.rollback.conf"
    assert conf_path.exists(), "bteam.rollback.conf 파일이 존재해야 합니다."
    content = conf_path.read_text(encoding="utf-8")

    # Blue legacy ports
    assert "server 127.0.0.1:5050;" in content
    assert "server 127.0.0.1:5173;" in content
    assert "server 127.0.0.1:8501;" in content
    assert "server 127.0.0.1:8002;" in content
