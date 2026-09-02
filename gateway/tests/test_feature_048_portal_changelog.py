from pathlib import Path
import pytest

GATEWAY_DIR = Path(__file__).resolve().parents[1]


def test_portal_cards_and_changelog_structure_red_gate():
    """RED GATE: Asserts gateway/html/index.html and changelog.html contain the
    Engineering Evolution 2x1 bento card, 7 milestones, and canonical /changelog link."""
    index_html = GATEWAY_DIR / "html" / "index.html"
    assert index_html.exists(), "gateway/html/index.html must exist"
    index_content = index_html.read_text(encoding="utf-8")
    assert "Engineering Evolution" in index_content, "RED GATE: index.html must have 2x1 Engineering Evolution card"
    assert "/changelog" in index_content, "RED GATE: index.html must link to canonical /changelog"

    changelog_html = GATEWAY_DIR / "html" / "changelog.html"
    assert changelog_html.exists(), "RED GATE: gateway/html/changelog.html must exist"
    changelog_content = changelog_html.read_text(encoding="utf-8")
    for milestone in ["chat_a", "chat_b", "model_gateway", "nginx_gateway", "oliview_web", "core", "pilos"]:
        assert milestone in changelog_content, f"RED GATE: changelog.html must include milestone {milestone}"

    for version_badge in ["v0.5.2-alpha", "v0.4.1-alpha", "v0.9.0-beta", "v0.8.5-beta", "v0.8.0-beta", "v0.7.0-alpha"]:
        assert version_badge in changelog_content, f"RED GATE: changelog.html must show version badge {version_badge}"
        if version_badge in ["v0.5.2-alpha", "v0.4.1-alpha", "v0.8.0-beta"]:
            assert version_badge in index_content, f"RED GATE: index.html must show service version badge {version_badge}"

    nginx_conf = GATEWAY_DIR / "nginx.conf"
    assert nginx_conf.exists(), "gateway/nginx.conf must exist"
    nginx_content = nginx_conf.read_text(encoding="utf-8")
    assert "location = /changelog_data.json" in nginx_content, "gateway/nginx.conf must route changelog_data.json"
    assert "location /changelog" in nginx_content, "gateway/nginx.conf must define canonical location /changelog"
    assert "changelog.html" in nginx_content, "gateway/nginx.conf must route /changelog to changelog.html"

    changelog_json = GATEWAY_DIR / "html" / "changelog_data.json"
    assert changelog_json.exists(), "gateway/html/changelog_data.json must exist"

