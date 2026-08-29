#!/usr/bin/env python3
"""마이그레이션 도구 공통 환경 변수 로더와 민감정보 마스커."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

_ENV_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.replace("\\n", "\n")


def parse_env_file(path: Path | str) -> dict[str, str]:
    """쉘 실행 없이 단순한 KEY=VALUE 형식의 env 파일을 읽습니다."""
    env_path = Path(path)
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        match = _ENV_LINE.match(raw_line)
        if not match or match.group(1).startswith("#"):
            continue
        values[match.group(1)] = _unquote(match.group(2))
    return values


def load_environment(
    project_root: Path | str, *, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """루트 `.env`, `ddns/.env`, 프로세스 환경을 병합합니다.

    파일 값은 root -> ddns 순으로 읽고, 프로세스 환경이 최종 우선순위를
    갖습니다. ddns 파일의 소문자 `domain`/`token`도 표준 대문자 키로
    정규화합니다.
    """
    root = Path(project_root).resolve()
    values: dict[str, str] = {}
    values.update(parse_env_file(root / ".env"))

    ddns_values = parse_env_file(root / "ddns" / ".env")
    if ddns_values.get("domain") and not values.get("DUCKDNS_DOMAIN"):
        values["DUCKDNS_DOMAIN"] = ddns_values["domain"]
    if ddns_values.get("token") and not values.get("DUCKDNS_TOKEN"):
        values["DUCKDNS_TOKEN"] = ddns_values["token"]
    values.update(
        {k: v for k, v in ddns_values.items() if k not in {"domain", "token"}}
    )

    values.update(dict(environ if environ is not None else os.environ))
    return values


def required_environment(values: Mapping[str, str], keys: list[str]) -> list[str]:
    """비어 있는 필수 환경 변수 이름만 반환합니다. 값은 반환하지 않습니다."""
    return [key for key in keys if not str(values.get(key, "")).strip()]


def mask_secret(value: object, *, visible: int = 2) -> str:
    """로그/manifest에 사용할 단방향이 아닌 표시용 마스킹 문자열."""
    text = "" if value is None else str(value)
    if not text:
        return "<unset>"
    if len(text) <= visible * 2:
        return "*" * len(text)
    return f"{text[:visible]}***{text[-visible:]}"


def masked_environment(
    values: Mapping[str, str], sensitive_keys: set[str] | None = None
) -> dict[str, str]:
    """환경 변수 전체를 복사하되 민감 키 값만 마스킹합니다."""
    keys = sensitive_keys or {
        key
        for key in values
        if any(
            token in key.upper()
            for token in ("PASSWORD", "TOKEN", "API_KEY", "SECRET", "PRIVATE_KEY")
        )
    }
    return {
        key: mask_secret(value) if key in keys else str(value)
        for key, value in values.items()
    }
