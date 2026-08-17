#!/usr/bin/env bash
# import_db_dump.sh: 1회성 대용량 DB 덤프 복원 Bash 스크립트
set -e

DUMP_FILE="${1:-pilos_v2.sql}"
CONTAINER_NAME="pilos-db"
DB_USER="root"
DB_PASSWORD="pilos_root_pass"
DB_NAME="pilos_v2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== A-Team DB 덤프 복원 워크플로우 시작 ==="

# 1. 네트워크 초기화
bash "$SCRIPT_DIR/init_network.sh"

# 2. .env 확인
if [ ! -f "$ROOT_DIR/pilos-sentiment-index/.env" ]; then
    echo ".env 파일 생성 중..."
    cp "$ROOT_DIR/pilos-sentiment-index/.env.example" "$ROOT_DIR/pilos-sentiment-index/.env"
fi

# 3. 덤프 파일 확인
if [ ! -f "$ROOT_DIR/$DUMP_FILE" ]; then
    echo "오류: 덤프 파일 $ROOT_DIR/$DUMP_FILE 을 찾을 수 없습니다."
    exit 1
fi

# 4. DB 서비스 기동
cd "$ROOT_DIR"
docker compose up -d db

# 5. 헬스체크 대기
echo "DBMS 컨테이너 헬스체크 대기 중..."
until [ "$(docker inspect --format='{{.State.Health.Status}}' $CONTAINER_NAME 2>/dev/null)" = "healthy" ]; do
    echo "대기 중..."
    sleep 3
done

echo "DBMS 컨테이너 준비 완료 (healthy)"

# 6. 복원 실행
echo "SQL 덤프 스트리밍 복원 시작 (2.69GB 적재 중, 잠시 기다려주세요)..."
docker exec -i $CONTAINER_NAME mysql -h 127.0.0.1 -u$DB_USER -p$DB_PASSWORD --default-character-set=utf8mb4 --max_allowed_packet=512M $DB_NAME < "$ROOT_DIR/$DUMP_FILE"

echo "덤프 복원 완료!"

# 7. 확인
docker exec -i $CONTAINER_NAME mysql -h 127.0.0.1 -u$DB_USER -p$DB_PASSWORD -e "USE $DB_NAME; SHOW TABLES;"
echo "=== A-Team DB 덤프 복원 완료 ==="
