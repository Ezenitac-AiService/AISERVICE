from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from oliview_core.session import RedisSessionStore


class CachePublisher(Protocol):
    def publish(self, namespace: str, version: int) -> None: ...


class RedisCachePublisher:
    """Persist cache-version events in the configured Redis namespace."""

    def __init__(self, endpoint: str):
        self._store = RedisSessionStore(endpoint, key_prefix="")

    def current(self, namespace_prefix: str) -> int:
        value = self._store._execute("GET", f"{namespace_prefix}:current")
        return int(str(value)) if value is not None else 1

    def publish(self, namespace: str, version: int) -> None:
        prefix, separator, version_text = namespace.rpartition(":v")
        if not separator or not version_text.isdigit():
            raise ValueError("cache namespace must end with a numeric version")
        current_key = f"{prefix}:current"
        current_result = self._store._execute("SET", current_key, version)
        if current_result != "OK":
            raise RuntimeError("Redis cache version publish was not acknowledged")
        result = self._store._execute("SET", f"{namespace}:version", version)
        if result != "OK":
            raise RuntimeError("Redis cache version publish was not acknowledged")


class LegacyCachePolicy(StrEnum):
    EXACT_TARGET = "EXACT_TARGET"
    BYPASS = "BYPASS"
    ISOLATED_REDIS = "ISOLATED_REDIS"


@dataclass
class CacheVersionManager:
    app_run_mode: str = "DEMO"
    report_version: int = 1
    rag_version: int = 1
    publisher: CachePublisher | None = None
    _product_versions: dict[tuple[str, str], int] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def version(self, product_id: int | str, kind: str) -> int:
        if kind not in {"report", "rag"}:
            raise ValueError("kind must be report or rag")
        return self._product_versions.get((str(product_id), kind), 1)

    def namespace(self, product_id: int | str, kind: str) -> str:
        if kind not in {"report", "rag"}:
            raise ValueError("kind must be report or rag")
        version = self.version(product_id, kind)
        return f"bteam:{self.app_run_mode}:product:{product_id}:{kind}:v{version}"

    def bump(self, product_id: int | str, kind: str) -> str:
        if kind not in {"report", "rag"}:
            raise ValueError("kind must be report or rag")
        key = (str(product_id), kind)
        current_version = self.version(product_id, kind)
        if self.publisher is not None:
            current = getattr(self.publisher, "current", None)
            if callable(current):
                current_version = max(
                    current_version,
                    int(
                        current(
                            f"bteam:{self.app_run_mode}:product:{product_id}:{kind}"
                        )
                    ),
                )
        next_version = current_version + 1
        namespace = (
            f"bteam:{self.app_run_mode}:product:{product_id}:{kind}:v{next_version}"
        )
        if self.publisher is not None:
            self.publisher.publish(namespace, next_version)
        self._product_versions[key] = next_version
        if kind == "report":
            self.report_version = max(self.report_version, next_version)
        else:
            self.rag_version = max(self.rag_version, next_version)
        return namespace


def classify_legacy_key(
    key: str, *, deterministic_target: bool = False
) -> LegacyCachePolicy:
    if deterministic_target and key.startswith("v1:rag:pool:"):
        return LegacyCachePolicy.EXACT_TARGET
    return LegacyCachePolicy.BYPASS
