# A-Team 컨테이너 개발 및 운영 가이드 (Container Setup Guide)

## 1. 개요

본 문서는 A-Team 프로젝트(`pilos-sentiment-index`)와 MySQL 데이터베이스(`pilos_v2.sql`, 2.69GB)를 Windows 11 + WSL2 + Rancher Desktop 환경에서 컨테이너 기반으로 구동하고, 독립 LLM 컨테이너와 연동하며, B-Team과의 포트 충돌 없이 서비스를 운영하기 위한 표준 가이드입니다.

---

## 2. 기본 구성 요약

* **Web Application**: `pilos-web` (`python:3.12-slim`, Gunicorn WSGI, 호스트 포트 `8080`)
* **DBMS**: `pilos-db` (`mysql:8.0`, UTF8MB4, 영속 볼륨 `ateam_db_data`, 호스트 포트 `3307`)
* **Network**: `aiservice-network` (공통 Docker 브리지 네트워크 - LLM 컨테이너와 공유)
* **초기 데이터**: 루트 디렉터리의 `pilos_v2.sql` (2.69GB)

---

## 3. 최초 설치 및 기동 절차

### 1단계: 사전 점검
* Rancher Desktop이 실행 중이고 Docker CLI가 활성화되어 있는지 확인합니다.
* 루트 디렉터리에 `pilos_v2.sql` 파일이 존재하는지 확인합니다.

### 2단계: 1회성 DB 초기화 및 덤프 적재
2.69GB 대용량 덤프 파일을 영속 볼륨에 적재합니다. (최초 1회만 수행)

```powershell
# Windows PowerShell
.\run_ateam_services.bat init-db

# 또는
.\scripts\import_db_dump.ps1
```

### 3단계: 전체 서비스 기동
웹 서비스 이미지를 빌드하고 백그라운드로 실행합니다.

```powershell
# Windows PowerShell
.\run_ateam_services.bat start

# 또는
docker compose up -d --build
```

---

## 4. 서비스 접속 정보

* **A-Team 메인 웹 대시보드**: [http://localhost:8080](http://localhost:8080)
* **주식 지수 목록 API**: [http://localhost:8080/api/stocks](http://localhost:8080/api/stocks)
* **챗봇 질의 API**: `POST http://localhost:8080/api/chat`
* **MySQL 데이터베이스**: `localhost:3307` (계정: `root`, 패스워드: `pilos_root_pass`, DB: `pilos_v2`)

---

## 5. 관리 및 운영 명령어

```powershell
# 서비스 상태 확인
.\run_ateam_services.bat status

# 실시간 로그 확인
.\run_ateam_services.bat logs

# 서비스 중지 (볼륨 데이터는 보존됨)
.\run_ateam_services.bat stop

# 서비스 재기동
.\run_ateam_services.bat restart
```

---

## 6. 포트 및 환경변수 변경 안내

B-Team 또는 다른 서비스와 포트가 겹치는 경우, `pilos-sentiment-index/.env` 파일에서 다음 항목을 변경하여 즉시 포트를 재조정할 수 있습니다:

```ini
WEB_PORT=8088    # 웹 서비스 포트 변경 예시
DB_PORT=3308     # MySQL 포트 변경 예시
```
변경 후 `docker compose up -d`를 실행하면 재적용됩니다.
