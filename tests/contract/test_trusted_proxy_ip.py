"""Trusted proxy and forwarded-header anti-spoofing contracts."""

from gateway.proxy_policy import parse_trusted_proxy_cidrs, resolve_client_ip
from scripts.render_gateway_config import render_nginx_conf


def test_trusted_proxy_configuration_is_explicit_and_validated() -> None:
    networks = parse_trusted_proxy_cidrs("10.0.0.0/8, 2001:db8::/32")
    assert len(networks) == 2
    try:
        parse_trusted_proxy_cidrs("not-a-cidr")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid trusted proxy CIDR was accepted")


def test_untrusted_peer_cannot_spoof_forwarded_client_ip() -> None:
    assert resolve_client_ip(
        "198.51.100.10",
        {"X-Forwarded-For": "203.0.113.99"},
        trusted_proxy_cidrs="10.0.0.0/8",
    ) == "198.51.100.10"


def test_trusted_peer_uses_single_valid_configured_header() -> None:
    assert resolve_client_ip(
        "10.1.2.3",
        {"X-Client-IP": "203.0.113.7"},
        trusted_proxy_cidrs="10.0.0.0/8",
        client_ip_header="X-Client-IP",
    ) == "203.0.113.7"
    assert resolve_client_ip(
        "10.1.2.3",
        {"X-Client-IP": "bad"},
        trusted_proxy_cidrs="10.0.0.0/8",
        client_ip_header="X-Client-IP",
    ) == "10.1.2.3"


def test_nginx_renderer_consumes_trusted_proxy_env_and_rejects_invalid_header() -> None:
    rendered = render_nginx_conf(
        {"TRUSTED_PROXY_CIDRS": "10.10.0.0/16", "TRUSTED_CLIENT_IP_HEADER": "X-Client-IP"}
    )
    assert "set_real_ip_from 10.10.0.0/16;" in rendered
    assert "real_ip_header X-Client-IP;" in rendered
    try:
        render_nginx_conf({"TRUSTED_CLIENT_IP_HEADER": "X-Client-IP; include /tmp/unsafe"})
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe trusted-client header was accepted")
    assert resolve_client_ip(
        "10.1.2.3",
        {"X-Client-IP": "203.0.113.7, 203.0.113.8"},
        trusted_proxy_cidrs="10.0.0.0/8",
        client_ip_header="X-Client-IP",
    ) == "10.1.2.3"
