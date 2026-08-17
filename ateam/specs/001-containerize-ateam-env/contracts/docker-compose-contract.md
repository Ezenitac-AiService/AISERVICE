# Interface Contract: Docker Compose & Container Specification

## 1. 개요

본 문서는 A-Team 컨테이너 인프라의 `docker-compose.yml` 인터페이스 규격 및 서비스 명세를 정의합니다.

---

## 2. Docker Compose 규격 정의

```yaml
version: "3.8"

networks:
  aiservice-network:
    name: aiservice-network
    external: true

volumes:
  ateam_db_data:
    name: ateam_db_data

services:
  db:
    container_name: pilos-db
    image: mysql:8.0
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD:-pilos_root_pass}
      MYSQL_DATABASE: ${DB_NAME:-pilos_v2}
      MYSQL_USER: ${DB_USER:-pilos_user}
      MYSQL_PASSWORD: ${DB_PASSWORD:-pilos_password}
      TZ: Asia/Seoul
    ports:
      - "${DB_PORT:-3307}:3306"
    volumes:
      - ateam_db_data:/var/lib/mysql
    networks:
      - aiservice-network
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u${DB_USER:-pilos_user}", "-p${DB_PASSWORD:-pilos_password}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  web:
    container_name: pilos-web
    build:
      context: ./pilos-sentiment-index
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file:
      - ./pilos-sentiment-index/.env
    ports:
      - "${WEB_PORT:-8080}:5000"
    depends_on:
      db:
        condition: service_healthy
    networks:
      - aiservice-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/api/stocks"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
```

---

## 3. 서비스 동작 규약 (Service SLA & Contract)

1. **DB 헬스체크 계약**:
   * `db` 서비스는 `mysqladmin ping` 명령을 통해 10초 간격으로 상태를 검사합니다.
   * `web` 서비스는 `db`의 `service_healthy` 조건이 충족된 후 기동을 시작합니다.
2. **포트 바인딩 계약**:
   * B-Team 및 로컬 포트 충돌을 회피하기 위해 기본 호스트 포트는 Web `8080`, DB `3307`로 고정합니다.
   * 환경 변수 `WEB_PORT`, `DB_PORT` 변경 시 즉시 오버라이드 가능해야 합니다.
3. **네트워크 통신 계약**:
   * 공유 브리지 네트워크 `aiservice-network`를 통해 동일 네트워크 내의 `llm-server` 컨테이너와 통신합니다.
