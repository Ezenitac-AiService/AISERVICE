"""test_server_health_diagnostics.py - LLM 서버 통합 진단 수트 단위 테스트
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 프로젝트 루트 경로 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.diagnose_server_health import (
    run_diagnostics,
    check_port_open,
    get_served_models,
    check_api_endpoints,
    check_dashboard_e2e
)
from src.core.network_detector import NetworkDetector


def test_network_detector_lan_ip_detection():
    lan_ips = NetworkDetector.get_active_lan_ips()
    assert isinstance(lan_ips, list)
    assert len(lan_ips) > 0
    assert not any(ip in ("127.0.0.1", "localhost") for ip in lan_ips)


def test_check_port_open_closed_port():
    # 사용되지 않는 가상의 높은 임의 포트 테스트
    is_open = check_port_open("127.0.0.1", 59999, timeout=0.2)
    assert is_open is False


@patch("httpx.Client.get")
def test_get_served_models_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "qwen3.5-4b"},
            {"id": "deepseek-r1-7b"}
        ]
    }
    mock_get.return_value = mock_resp

    models = get_served_models("http://10.0.0.15:8081")
    assert "qwen3.5-4b" in models
    assert "deepseek-r1-7b" in models


@patch("httpx.Client.get")
@patch("httpx.Client.post")
def test_check_api_endpoints_mock(mock_post, mock_get):
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get.return_value = mock_get_resp

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post.return_value = mock_post_resp

    endpoints = check_api_endpoints("http://10.0.0.15:8081")
    assert endpoints["/v1/models"] is True
    assert endpoints["/health"] is True
    assert endpoints["/v1/chat/completions"] is True


@patch("httpx.Client.get")
def test_check_dashboard_e2e_mock(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><title>vLLM Serving Dashboard</title></html>"
    mock_get.return_value = mock_resp

    status = check_dashboard_e2e("http://10.0.0.15:8082")
    assert status is True


def test_run_diagnostics_structure():
    report = run_diagnostics(verbose=False)
    assert "detected_lan_ip" in report
    assert "served_models" in report
    assert "api_status" in report
    assert "firewall_ports" in report
    assert "dashboard_e2e_status" in report
    assert "is_healthy" in report
    assert report["detected_lan_ip"] != ""
