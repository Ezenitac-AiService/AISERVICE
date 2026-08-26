"""DB 연결을 제공하는 storage 계층 모듈.

.env 의 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 로 MySQL(SQLAlchemy+PyMySQL)
엔진을 만든다. 엔진은 프로세스당 한 번만 생성해 재사용한다(lru_cache).
"""
import logging
import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

load_dotenv()

logger = logging.getLogger(__name__)

def _require_env():
    """DB 접속에 필요한 환경변수를 모아 반환한다(누락 시 명확히 실패)."""
    cfg = {
        "host": os.getenv("DB_HOST", os.getenv("PILOS_DB_HOST", "pilos-db")),
        "port": os.getenv("DB_PORT", os.getenv("PILOS_DB_PORT", "3306")),
        "user": os.getenv("DB_USER", os.getenv("PILOS_DB_USER", "pilos_user")),
        "password": os.getenv("DB_PASSWORD", os.getenv("PILOS_DB_PASSWORD", "pilos_password")),
        "name": os.getenv("DB_NAME", os.getenv("PILOS_DB_NAME", "pilos_v2")),
    }
    missing = [k for k in ("host", "user", "password", "name") if not cfg[k]]
    if missing:
        raise RuntimeError(
            f".env 에 DB 설정이 없습니다: {missing} "
            f"(DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 확인)"
        )
    return cfg


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """MySQL 엔진을 생성해 반환한다(프로세스당 1회, 이후 캐시).

    pool_pre_ping 으로 죽은 커넥션을 걸러내고, pool_recycle 로 오래된 커넥션을 재활용한다.
    """
    cfg = _require_env()
    url = URL.create(
        "mysql+pymysql",
        username=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=int(cfg["port"]) if cfg["port"] else 3306,
        database=cfg["name"],
        query={"charset": "utf8mb4"},
    )
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600, future=True)
    logger.info(f"DB 엔진 생성: {cfg['host']}:{cfg['port'] or 3306}/{cfg['name']}")
    return engine
