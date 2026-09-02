#!/usr/bin/env python
"""
Gateway Configuration Template Renderer (SSOT / Constitution Principle VII).
Validates environment against contracts/runtime_environment_schema.json
and renders gateway/nginx.conf from gateway/nginx.conf.template.
"""

import json
import os
import re
import sys
from pathlib import Path
from jsonschema import Draft202012Validator, ValidationError

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "specs" / "048-anti-fictional-user-and-citation-fidelity" / "contracts"
SCHEMA_PATH = CONTRACTS_DIR / "runtime_environment_schema.json"
TEMPLATE_PATH = ROOT_DIR / "gateway" / "nginx.conf.template"
OUTPUT_PATH = ROOT_DIR / "gateway" / "nginx.conf"

if str(ROOT_DIR / "bteam") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "bteam"))


def load_and_validate_env(custom_env: dict | None = None) -> dict:
    if custom_env is not None:
        raw_env = dict(custom_env)
    else:
        # Load defaults from CoreSettings
        try:
            from oliview_core.config import CoreSettings
            defaults = CoreSettings().model_dump()
        except Exception:
            defaults = {}
        raw_env = {**defaults, **dict(os.environ)}

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Cast integer fields if coming from os.environ
    normalized = {}
    for k, v in raw_env.items():
        if k in schema.get("properties", {}):
            prop_type = schema["properties"][k].get("type")
            if prop_type == "integer":
                try:
                    normalized[k] = int(v)
                except (ValueError, TypeError):
                    normalized[k] = v
            elif prop_type == "boolean":
                if isinstance(v, str):
                    normalized[k] = v.lower() in ("true", "1", "yes")
                else:
                    normalized[k] = bool(v)
            else:
                normalized[k] = v
        else:
            normalized[k] = v

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(normalized), key=lambda e: e.path)
    if errors:
        msg = "\n".join([f"  - {e.message} (at {list(e.path)})" for e in errors])
        raise ValidationError(f"Runtime environment schema validation failed:\n{msg}")

    return normalized


def render_nginx_conf(env_dict: dict) -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Nginx template not found: {TEMPLATE_PATH}")

    template_content = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Substitute ${VAR}
    def replace_var(match):
        var_name = match.group(1)
        if var_name in env_dict:
            return str(env_dict[var_name])
        raise KeyError(f"Unresolved environment variable in template: ${{{var_name}}}")

    rendered = re.sub(r"\$\{([A-Za-z0-9_]+)\}", replace_var, template_content)

    # Check for any remaining unresolved variables
    unresolved = re.findall(r"\$\{([A-Za-z0-9_]+)\}", rendered)
    if unresolved:
        raise ValueError(f"Unresolved variables remaining in rendered Nginx config: {unresolved}")

    return rendered


def render_and_write(custom_env: dict | None = None) -> Path:
    env_dict = load_and_validate_env(custom_env)
    rendered_content = render_nginx_conf(env_dict)
    OUTPUT_PATH.write_text(rendered_content, encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    try:
        out = render_and_write()
        print(f"[SUCCESS] Rendered gateway Nginx configuration to {out}")
    except Exception as exc:
        print(f"[ERROR] Failed to render gateway Nginx configuration: {exc}", file=sys.stderr)
        sys.exit(1)
