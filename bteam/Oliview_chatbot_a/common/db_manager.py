"""
공통 MySQL DB 연결 관리

사용 예시
----------
from common.db_manager import get_connection

conn = get_connection()

with conn.cursor() as cursor:
    cursor.execute("SELECT * FROM vw_chroma_review_sentences")
    rows = cursor.fetchall()

conn.close()
"""

import os
import pymysql
from dotenv import load_dotenv

# .env 환경변수 로드
load_dotenv()


def get_connection():
    """
    MySQL 연결 객체를 반환합니다.
    """

    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )