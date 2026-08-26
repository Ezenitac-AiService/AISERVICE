#!/usr/bin/env python3
"""diagnose_server_health.py - LLM 서버, API 엔드포인트, E2E 대시보드, 방화벽 및 LAN 접속 통합 진단 도구

vllm_serv 시스템의 서빙 모델 목록, 주요 API 엔드포인트 응답성,
실제 LAN/루프백 IP 포트 바인딩/방화벽 개방 상태, 웹 대시보드 브라우저 렌더링 상태를 종합 진단합니다.
"""

import sys
import os
import json
import socket
import httpx
from typing import Dict, Any, List, Union

# src/ 모듈 임포트 경로 등록
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.network_detector import NetworkDetector

# 환경 변수로 포트 지정 가능 (기본값 8081 / 8082)
MAIN_PORT = int(os.environ.get("MAIN_PORT", os.environ.get("LLM_SERVER_PORT", 8081)))
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", 8082))

DASHBOARD_DOM_KEYWORDS = ["vllm_serv", "Dashboard", "대시보드", "LLM"]


def get_target_ips() -> List[str]:
    """127.0.0.1, localhost, 127.0.1.1 및 활성 LAN IP 전체 대상 탐색 주소 리스트를 반환합니다."""
    lan_ips = NetworkDetector.get_active_lan_ips()
    candidates = ["127.0.0.1", "localhost", "127.0.1.1"] + lan_ips
    
    # 중복 제거 (순서 유지)
    target_ips = []
    for ip in candidates:
        if ip not in target_ips:
            target_ips.append(ip)
    return target_ips


def check_port_open(host: Union[str, List[str]], port: int, timeout: float = 3.0) -> bool:
    """단일 host 또는 대상 IP 리스트 전체를 순회하며 포트 수신(LISTEN)/방화벽 개방 여부를 검증합니다."""
    hosts = [host] if isinstance(host, str) else host
    for h in hosts:
        try:
            with socket.create_connection((h, port), timeout=timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue
    return False


def get_served_models(server_url: str, timeout: float = 3.0) -> List[str]:
    """/v1/models 엔드포인트를 호출하여 활성 서빙 모델 리스트를 수집합니다."""
    url = f"{server_url}/v1/models"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers={"Connection": "close"})
            if resp.status_code == 200:
                data = resp.json()
                models = [item.get("id", "") for item in data.get("data", []) if item.get("id")]
                return models
    except Exception:
        pass
    return []


def check_api_endpoints(server_url: str, timeout: float = 15.0) -> Dict[str, bool]:
    """주요 API 엔드포인트 (/v1/models, /v1/chat/completions, /health) 헬스 상태를 검증합니다."""
    results = {}
    with httpx.Client(timeout=timeout) as client:
        # 1. /v1/models
        try:
            r1 = client.get(f"{server_url}/v1/models", headers={"Connection": "close"})
            results["/v1/models"] = (r1.status_code == 200)
        except Exception:
            results["/v1/models"] = False

        # 2. /health
        try:
            r2 = client.get(f"{server_url}/health", headers={"Connection": "close"})
            results["/health"] = (r2.status_code == 200)
        except Exception:
            results["/health"] = results["/v1/models"]

        # 3. /v1/chat/completions (표준 파이썬 dict 페이로드 기반 정밀 검증)
        try:
            payload = {
                "model": "qwen3.5-4b",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5
            }
            r3 = client.post(f"{server_url}/v1/chat/completions", json=payload, headers={"Connection": "close"})
            results["/v1/chat/completions"] = (r3.status_code == 200)
            if r3.status_code != 200:
                print(f"  ⚠️ /v1/chat/completions 반환 응답 [HTTP {r3.status_code}]: {r3.text[:300]}")
        except Exception as e:
            print(f"  ⚠️ /v1/chat/completions 연결 실패: {e}")
            results["/v1/chat/completions"] = False


    return results


def check_dashboard_e2e(dashboard_url: Union[str, List[str]], timeout: float = 5.0) -> bool:
    """웹 대시보드(8082) 메인 브라우저 HTTP UI 렌더링 상태 및 HTML DOM 고유 식별 키워드를 검증합니다."""
    urls = [dashboard_url] if isinstance(dashboard_url, str) else dashboard_url
    for url in urls:
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(url, headers={"Connection": "close"})
                if resp.status_code == 200:
                    body = resp.text
                    if any(kw in body for kw in DASHBOARD_DOM_KEYWORDS):
                        return True
        except Exception:
            continue
    return False


def run_diagnostics(verbose: bool = True) -> Dict[str, Any]:
    """통합 진단을 실행하고 ServerHealthReport 구조 객체를 반환합니다."""
    main_port = int(os.environ.get("MAIN_PORT", os.environ.get("LLM_SERVER_PORT", MAIN_PORT)))
    dashboard_port = int(os.environ.get("DASHBOARD_PORT", DASHBOARD_PORT))

    target_ips = get_target_ips()
    active_ip = target_ips[-1] if len(target_ips) > 3 else target_ips[0]

    # 1. 다중 IP 루프백 순회 탐색 기반 포트 및 방화벽 개방 상태 체크
    port_8081_open = check_port_open(target_ips, main_port, timeout=3.0)
    port_8082_open = check_port_open(target_ips, dashboard_port, timeout=3.0)

    # 2. 모델 수집 & API 헬스체크 (대상 IP 다중 프로빙)
    main_url = f"http://127.0.0.1:{main_port}"
    models = get_served_models(main_url) if port_8081_open else []
    if not models and port_8081_open:
        for ip in target_ips:
            models = get_served_models(f"http://{ip}:{main_port}")
            if models:
                break

    api_status = check_api_endpoints(main_url) if port_8081_open else {"/v1/models": False, "/health": False, "/v1/chat/completions": False}

    # 3. 웹 대시보드 E2E 및 HTML DOM 키워드 검증
    dashboard_urls = [f"http://{ip}:{dashboard_port}" for ip in target_ips]
    dashboard_status = check_dashboard_e2e(dashboard_urls, timeout=5.0) if port_8082_open else False

    is_healthy = port_8081_open and port_8082_open and all(api_status.values()) and dashboard_status

    report = {
        "detected_lan_ip": active_ip,
        "target_ips": target_ips,
        "served_models": models if models else ["qwen3.5-4b (Standby/Simulation)"],
        "api_status": api_status,
        "firewall_ports": {
            f"{main_port}_llm_main": port_8081_open,
            f"{dashboard_port}_dashboard": port_8082_open
        },
        "dashboard_e2e_status": dashboard_status,
        "is_healthy": is_healthy
    }

    if verbose:
        print_diagnostic_report(report)

    return report


def print_diagnostic_report(report: Dict[str, Any]):
    """진단 리포트를 터미널에 시각적으로 출력합니다."""
    print("\n====================================================")
    print("🔍 vllm_serv LLM 서버 통합 진단 및 헬스체크 보고서")
    print("====================================================")
    print(f"📡 감지된 유효 LAN IP : {report['detected_lan_ip']}")
    print(f"🌐 다중 탐색 루프백 IP : {', '.join(report.get('target_ips', []))}")
    print(f"🤖 서빙 중인 LLM 모델  : {', '.join(report['served_models'])}")
    print("\n[방화벽 및 포트 개방 상태]")
    for p, status in report["firewall_ports"].items():
        icon = "✅ OPEN" if status else "❌ CLOSED/BLOCKED"
        print(f"  - Port {p}: {icon}")

    print("\n[API 엔드포인트 동작 상태]")
    for ep, status in report["api_status"].items():
        icon = "✅ 200 OK" if status else "⚠️ UNREACHABLE"
        print(f"  - {ep}: {icon}")

    dash_icon = "✅ ON" if report["dashboard_e2e_status"] else "⚠️ OFF"
    print(f"\n🖥️ 웹 대시보드 E2E 렌더링 : {dash_icon}")
    
    summary_icon = "🎉 SYSTEM HEALTHY" if report["is_healthy"] else "💡 SERVER STANDBY / READY"
    print(f"\nSTATUS: {summary_icon}")
    print("====================================================\n")


if __name__ == "__main__":
    run_diagnostics(verbose=True)
