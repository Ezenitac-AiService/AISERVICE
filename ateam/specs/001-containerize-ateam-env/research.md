# Implementation Research: A-Team 컨테이너 기반 개발 및 서비스 환경 구축

## 연구 개요

본 문서는 A-Team 프로젝트(`pilos-sentiment-index`)와 대용량 데이터베이스 덤프(`pilos_v2.sql`, 약 2.69GB)를 Windows 11 + WSL2 + Rancher Desktop 환경에서 성공적으로 컨테이너화하고, 독립 실행 중인 LLM 추론 서버 컨테이너와 연동하며, B-Team과의 포트 충돌을 방지하기 위한 기술적 연구 결과를 정리합니다.

---

## 핵심 기술 의사결정 및 분석

### 1. Python 웹 서비스 컨테이너화 전략 (Base Image & Dependency Management)

* **Decision**: `python:3.12-slim` 공식 이미지를 베이스로 사용하고, `uv` 또는 표준 `pip` 기반의 휠 빌드 캐시를 활용하여 경량화된 웹 애플리케이션 컨테이너를 빌드합니다.
* **Rationale**:
  * `pyproject.toml`에 명시된 `requires-python = ">=3.12,<3.13"` 요구사항을 충족합니다.
  * C-extension 라이브러리(`kiwipiepy`, `scikit-learn`, `numpy`, `pandas`)의 원활한 설치를 위해 빌드 시점에 필수 빌드 도구(`build-essential` 등)를 임시 설치한 후 정리(multi-stage 또는 단일 계층 최적화)하여 이미지 용량을 최소화합니다.
  * 프로덕션 및 로컬 서비스 서빙을 위해 Gunicorn WSGI 서버 또는 안정적인 Flask 서빙 명령어를 엔트리포인트로 설정합니다.
* **Alternatives considered**:
  * `python:3.12-alpine`: Alpine의 musl libc로 인해 `kiwipiepy` 및 C-바인딩 패키지 컴파일/호환성 문제가 발생할 가능성이 높아 기각.
  * `Full python:3.12 (Debian)`: 이미지 용량이 1GB 이상으로 비대해지므로 경량화된 `slim` 채택.

### 2. 대용량 DB 덤프(2.69GB `pilos_v2.sql`) 적재 및 영속 볼륨 전략

* **Decision**: MySQL 8.0/8.4 공식 이미지를 기반으로 명명된 볼륨(`named volume`, 예: `ateam_mysql_data`)을 구성하고, 1회성 DB 초기화 스크립트(`init-db.sh` 또는 compose 프로필)를 통해 덤프를 안전하게 적재합니다.
* **Rationale**:
  * 2.69GB 크기의 대용량 SQL 파일을 `/docker-entrypoint-initdb.d`에 단순 마운트할 경우, 최초 컨테이너 기동 시 실행 타임아웃이나 컨테이너 재시작 루프가 발생할 위험이 있습니다.
  * MySQL 컨테이너가 정상 기동(Healthcheck `healthy` 상태)된 후 `docker exec -i <db-container> mysql -u<user> -p<password> <database> < pilos_v2.sql` 방식으로 스트리밍 복원하면 진행 상태를 명확히 모니터링할 수 있고 메모리 부담을 최소화할 수 있습니다.
  * 복원 완료 후에는 영속 볼륨에 바이너리 데이터가 영구 저장되므로, 컨테이너를 재시작하거나 재생성해도 덤프를 다시 읽을 필요가 없어 기동 시간이 3초 이내로 단축됩니다.
* **Alternatives considered**:
  * 호스트 디렉터리 직접 바인드 마운트: Windows WSL2 환경에서 NTFS 바인드 마운트 시 I/O 성능 저하 및 권한 이슈가 발생할 수 있어 WSL2 네이티브 Named Volume 사용 결정.

### 3. LLM 컨테이너 연동 및 Docker 네트워크 아키텍처

* **Decision**: 사전 정의된 외부 Docker 브리지 네트워크(예: `aiservice-network`)를 생성하고, A-Team 서비스 컨테이너와 LLM 서빙 컨테이너를 해당 네트워크에 연결하여 컨테이너 이름(DNS) 기반으로 통신합니다.
* **Rationale**:
  * 호스트 포트 포워딩을 거치지 않으므로 호스트 IP 변경(WSL2 IP 변경 문제)에 영향을 받지 않고 고정된 컨테이너 이름(예: `http://llm-server:8000/v1`)으로 안정적인 내부 통신이 가능합니다.
  * A-Team 컨테이너의 `.env` 파일에 `LLM_BASE_URL=http://<llm-container-name>:<port>/v1`, `EMBEDDING_BASE_URL=http://<llm-container-name>:<port>/v1` 등으로 설정하여 유연하게 주입할 수 있습니다.
* **Alternatives considered**:
  * `host.docker.internal` 경유: Windows/WSL2 환경 간 포트 포워딩 설정에 따라 호스트 방화벽이나 포트 점유 문제가 생길 수 있어 Docker 전용 브리지 네트워크 방식 채택.

### 4. B-Team과의 포트 충돌 방지 및 멀티 서비스 격리

* **Decision**: A-Team 전용 포트 대역(Web: `8080`, MySQL: `3307`)을 기본값으로 지정하고, 모든 포트 매핑을 `.env`의 환경 변수(`WEB_PORT`, `DB_PORT`)로 바인딩합니다.
* **Rationale**:
  * B-Team이 기본 웹 포트(`80` 또는 `5000`) 및 표준 MySQL 포트(`3306`)를 점유하고 있더라도 충돌 없이 동시에 실행될 수 있습니다.
  * 포트 충돌 발생 시 소스 코드나 compose 파일을 수정하지 않고 `.env` 파일의 한 줄만 변경하여 즉시 해결 가능합니다.
* **Alternatives considered**:
  * 역방향 프록시(Nginx / Traefik) 단일 진입점: 팀 간 추가적인 라우팅 설정 종속성이 생겨 YAGNI 원칙에 따라 각 팀 고유 포트 바인딩 방식 채택.

### 5. Windows 11 + WSL2 + Rancher Desktop 실행 환경 호환성

* **Decision**: 표준 `docker-compose.yml` (Compose v2 규격) 및 크로스 플랫폼 실행 스크립트(PowerShell / Bash)를 제공합니다.
* **Rationale**:
  * Rancher Desktop의 Docker CLI 및 `nerdctl` 런타임과 100% 호환됩니다.
  * 줄바꿈 문자(CRLF/LF)로 인한 쉘 스크립트 실행 오류를 방지하기 위해 컨테이너 내부 실행 스크립트는 `.gitattributes`에 `text eol=lf`를 적용합니다.

---

## 결론 및 권장 구현 스택

| 컴포넌트 | 선택 기술 / 사양 | 비고 |
|---|---|---|
| **Web Service Runtime** | `python:3.12-slim` + Flask / Gunicorn | 경량화 및 C-extension 종속성 해결 |
| **DBMS Runtime** | `mysql:8.0` (또는 `mysql:8.4`) | `pilos_v2.sql` 덤프 호환 |
| **Data Volume** | Docker Named Volume (`ateam_db_data`) | WSL2 네이티브 I/O 성능 및 영속성 보장 |
| **Network** | User-defined Bridge Network (`aiservice-network`) | LLM 컨테이너와 컨테이너명(DNS) 통신 |
| **Port Mapping** | Web `8080:5000`, DB `3307:3306` | B-Team 충돌 방지, `.env` 오버라이드 지원 |
