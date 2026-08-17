"""Database Restoration Verification Script

Connects to the MySQL database and verifies table integrity and record counts.
"""

import os
import sys
import pymysql

def verify_database():
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "3307"))
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "pilos_root_pass")
    db_name = os.getenv("DB_NAME", "pilos_v2")

    print(f"Connecting to database: {user}@{host}:{port}/{db_name}")

    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"[ERROR] Failed to connect to MySQL: {e}", file=sys.stderr)
        return False

    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            print(f"\n[OK] Found {len(tables)} tables in database '{db_name}':")
            for t in tables:
                table_name = list(t.values())[0]
                cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table_name}`;")
                count_res = cursor.fetchone()
                print(f"  - {table_name}: {count_res['cnt']:,} rows")
            
            if len(tables) == 0:
                print("[WARNING] Database exists but has 0 tables.", file=sys.stderr)
                return False
                
            print("\n[SUCCESS] Database verification passed!")
            return True
    except Exception as e:
        print(f"[ERROR] Query execution failed: {e}", file=sys.stderr)
        return False
    finally:
        connection.close()

if __name__ == "__main__":
    success = verify_database()
    sys.exit(0 if success else 1)
