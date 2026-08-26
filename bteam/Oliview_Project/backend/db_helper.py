import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

def get_db_config():
    """표준 및 레거시 환경변수로부터 데이터베이스 접속 설정을 로드합니다."""
    host = os.getenv("DB_HOST") or os.getenv("host") or "localhost"
    port = int(os.getenv("DB_PORT", 3306))
    user = os.getenv("DB_USER") or os.getenv("ID") or "GP"
    password = os.getenv("DB_PASSWORD") or os.getenv("PW") or "GP123!"
    database = os.getenv("DB_NAME") or os.getenv("DB_NAME3") or os.getenv("DBName") or "oliview_project"
    
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor
    }

def get_db_connection():
    """데이터베이스 연결 객체를 생성하여 반환합니다."""
    config = get_db_config()
    return pymysql.connect(**config)
