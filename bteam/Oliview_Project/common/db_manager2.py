import os
from pathlib import Path
from typing import Any

import mysql.connector
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE, override=True)


class DBManager:
    def __init__(self) -> None:
        self.connection = None
        self.cursor = None

    def connect(self) -> None:
        self.connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "192.168.0.8"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME2"),
            charset="utf8mb4",
        )

        # buffered=True를 설정하면 조회 결과가 남아서 생기는 문제를 줄일 수 있음
        self.cursor = self.connection.cursor(
            dictionary=True,
            buffered=True,
        )

        print("DB 연결 성공")

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | None = None,
    ) -> None:
        self._check_connection()
        self.cursor.execute(sql, params or ())

    def executemany(
        self,
        sql: str,
        params,
    ) -> None:
        self._check_connection()
        self.cursor.executemany(sql, params)

    def fetchone(self):
        self._check_connection()
        return self.cursor.fetchone()

    def fetchall(self):
        self._check_connection()
        return self.cursor.fetchall()

    def commit(self) -> None:
        if self.connection is not None:
            self.connection.commit()

    def rollback(self) -> None:
        if self.connection is not None:
            self.connection.rollback()

    def close(self) -> None:
        if self.cursor is not None:
            self.cursor.close()
            self.cursor = None

        if self.connection is not None:
            if self.connection.is_connected():
                self.connection.close()

            self.connection = None

        print("DB 연결 종료")

    def _check_connection(self) -> None:
        # fetchone 실행 전에 is_connected()를 호출하면
        # 조회 결과가 남아 있을 때 잘못된 판단이 발생할 수 있음
        if self.connection is None:
            raise RuntimeError("DB connection 객체가 없습니다.")

        if self.cursor is None:
            raise RuntimeError("DB cursor가 없습니다.")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()

        self.close()

        return False