#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gateway Configuration Template Renderer (SSOT / Constitution Principle VII).
Renders gateway/nginx.conf from gateway/nginx.conf.template with secret-free defaults.
Prevents template drift and ensures no hardcoded legacy domains exist.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT_DIR / "gateway" / "nginx.conf.template"
OUTPUT_PATH = ROOT_DIR / "gateway" / "nginx.conf"

DEFAULT_GATEWAY_ENV = {
    "GATEWAY_SERVER_NAMES": "_",
    "OLIVIEW_BACKEND_UPSTREAM": "http://oliview_backend:5050",
    "OLIVIEW_FRONTEND_UPSTREAM": "http://oliview_frontend:5173",
    "CHATBOT_A_UPSTREAM": "http://oliview_chatbot_a:8501",
    "CHATBOT_B_UPSTREAM": "http://oliview_chatbot_b:8002",
    "PILOS_WEB_UPSTREAM": "http://pilos_web:5000",
}


def render_nginx_conf(env_dict: dict[str, str] | None = None) -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Nginx template not found: {TEMPLATE_PATH}")

    merged_env = dict(DEFAULT_GATEWAY_ENV)
    merged_env.update(dict(os.environ))
    if env_dict:
        merged_env.update(env_dict)

    template_content = TEMPLATE_PATH.read_text(encoding="utf-8")

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in merged_env:
            return str(merged_env[var_name])
        raise KeyError(f"Unresolved environment variable in template: ${{{var_name}}}")

    rendered = re.sub(r"\$\{([A-Za-z0-9_]+)\}", replace_var, template_content)

    unresolved = re.findall(r"\$\{([A-Za-z0-9_]+)\}", rendered)
    if unresolved:
        raise ValueError(f"Unresolved variables remaining in rendered Nginx config: {unresolved}")

    # Assert no legacy duckdns domains remain
    if "duckdns.org" in rendered:
        raise ValueError("Legacy duckdns.org domain detected in rendered Nginx config!")

    return rendered


def render_and_write(custom_env: dict | None = None) -> Path:
    rendered_content = render_nginx_conf(custom_env)
    OUTPUT_PATH.write_text(rendered_content, encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    try:
        out = render_and_write()
        print(f"[SUCCESS] Rendered gateway Nginx configuration to {out}")
    except Exception as exc:
        print(f"[ERROR] Failed to render gateway Nginx configuration: {exc}", file=sys.stderr)
        sys.exit(1)
