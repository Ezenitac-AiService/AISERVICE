from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

SENSITIVE_KEY_PARTS = (
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "cookie",
)


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: "[REDACTED]" if is_sensitive_key(key) else value
        for key, value in values.items()
    }


class JsonRedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "event", None)
        if isinstance(extra, Mapping):
            payload.update(redact_mapping(extra))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonRedactingFormatter())
        root.addHandler(handler)
    root.setLevel(level)
