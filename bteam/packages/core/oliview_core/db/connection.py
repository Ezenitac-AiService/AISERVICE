from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class DatabaseSettings:
    host: str = "localhost"
    port: int = 3306
    database: str = "cosmetic_db"
    user: str = ""
    password: str = ""

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> DatabaseSettings:
        source: Mapping[str, str] = values if values is not None else os.environ
        return cls(
            host=source.get("MYSQL_HOST", source.get("DB_HOST", "localhost")),
            port=int(source.get("MYSQL_PORT", source.get("DB_PORT", "3306"))),
            database=source.get("MYSQL_DATABASE", source.get("DB_NAME", "cosmetic_db")),
            user=source.get("MYSQL_USER", source.get("DB_USER", "")),
            password=source.get("MYSQL_PASSWORD", source.get("DB_PASSWORD", "")),
        )


def mysql_url(settings: DatabaseSettings) -> str:
    password = quote_plus(settings.password)
    return f"mysql+pymysql://{quote_plus(settings.user)}:{password}@{settings.host}:{settings.port}/{settings.database}?charset=utf8mb4"


def create_mysql_engine(
    settings: DatabaseSettings | None = None, *, pool_size: int = 5
) -> Engine:
    config = settings or DatabaseSettings.from_env()
    return create_engine(
        mysql_url(config),
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=pool_size,
        future=True,
    )


@contextlib.contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextlib.contextmanager
def sqlite_transaction(path: str = ":memory:") -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()
