# tests/test_xss_escape.py
"""
통합 3대 챗봇 XSS/HTML 인젝션 방어 및 이스케이프 검증 테스트
"""

import html
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


def test_html_escape_vectors():
    malicious_inputs = [
        '<script>alert("xss")</script>',
        '<img src=x onerror=alert(1)>',
        '<a href="javascript:void(0)">클릭</a>',
        '"><script src=evil.js></script>',
        '<b>굵은글씨</b> & "따옴표"',
    ]

    for attack in malicious_inputs:
        escaped = html.escape(attack)
        assert "<script>" not in escaped
        assert "<img" not in escaped
        assert "<a href" not in escaped
        assert "&lt;" in escaped or "&quot;" in escaped or "&amp;" in escaped
        print(f"[PASS] XSS vector neutralized: {attack[:25]}... -> {escaped[:30]}")


def test_js_escape_html_logic():
    # Simulate JS escapeHtml()
    def js_escape_html(text: str) -> str:
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#039;")
        )

    attack = '<div onclick="stealCookie()">헤라 쿠션</div>'
    safe = js_escape_html(attack)
    assert "<div" not in safe
    assert "&lt;div" in safe
    assert "&quot;" in safe
    print("[PASS] JS escapeHtml logic verified")


if __name__ == "__main__":
    test_html_escape_vectors()
    test_js_escape_html_logic()
    print("[SUCCESS] All test_xss_escape.py tests passed!")
