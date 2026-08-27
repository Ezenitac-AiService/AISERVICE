from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping

from oliview_core.gateway import validate_production_topology

from oliview_core.config import Settings


def parse_endpoints(raw: str) -> list[dict[str, object]]:
    value = json.loads(raw)
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise TypeError(
            "MODEL_GATEWAY_ENDPOINTS/GATEWAY_ENDPOINTS must be a JSON list"
        )
    return [dict(item) for item in value]


def validate_environment(values: Mapping[str, str] | None = None) -> None:
    source: Mapping[str, str] = values if values is not None else os.environ
    settings = Settings.from_env(source)
    if settings.app_run_mode != "PRODUCTION":
        return
    endpoints = parse_endpoints(settings.model_gateway_endpoints)
    validate_production_topology(
        endpoints,
        redis_ha_ready=source.get("REDIS_HA_QUORUM", "")
        in {"3", "ready", "READY"},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    validate_environment()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
