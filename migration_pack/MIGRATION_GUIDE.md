# 📦 AISERVICE 크로스 플랫폼 마이그레이션 실행 매뉴얼 (MIGRATION_GUIDE.md)

AISERVICE 전체 멀티 에이전트 서비스 생태계(A-Team Pilos, B-Team Oliview, Model Gateway, Redis, Nginx 프록시)와 컨테이너 내부 데이터베이스(`pilos_v2` 3.4GB, `oliview_project` 950MB)를 **다른 플랫폼(Linux Ubuntu/Debian/RHEL, AWS EC2, GCP Compute Engine, On-Premise GPU 서버, 다른 Windows 호스트 등)**으로 무손실, 원클릭 이전하기 위한 완전 안내서입니다.

---

## 1. 📋 마이그레이션 팩 구성 (`migration_pack/`)

```text
migration_pack/
├── database/                        # 무손실 압축 DB 백업
│   ├── pilos_v2.sql.gz              # A-Team Pilos MySQL 8.0 덤프 (481.2 MB 압축본 / 원본 2.8GB)
│   ├── oliview_project.sql.gz       # B-Team Oliview 1024차원 벡터 덤프 (512.4 MB 압축본 / 원본 1.2GB)
│   └── checksums.sha256             # SHA-256 비트 무결성 체크섬 매니페스트
├── scripts/                         # 원클릭 자동화 도구 (Linux Bash & Windows Batch)
│   ├── export_databases.sh/.bat     # [소스 호스트] DB 덤프 및 해시 생성 도구
│   ├── bootstrap_restore.sh/.bat    # [타겟 호스트] 원클릭 DB 복원 및 서비스 오케스트레이터
│   ├── pack_archive.sh/.bat         # [소스 호스트] 단일 아카이브(.tar.gz / .zip) 압축 도구
│   ├── export_offline_models.sh/.bat# [소스 호스트] 폐쇄망용 오프라인 모델 가중치 번들러 (선택)
│   ├── configure_env.py             # [타겟 호스트] 환경 변수 프로파일러 및 검증기
│   └── verify_migration.py          # [타겟 호스트] 11개 엔드포인트 E2E 자동 검증기
├── config/                          # 환경 설정 매트릭스
│   ├── .env.migration.template      # 통합 환경 변수 프로파일 템플릿
│   ├── ddns.env.template            # DuckDNS 및 도메인 템플릿
│   └── nginx.conf                   # Nginx 역방향 프록시 설정
├── docker-compose.yml               # 다중 플랫폼 호환 Docker Compose 매니페스트
├── migration_manifest.json          # 마이그레이션 메타데이터 정본
└── MIGRATION_GUIDE.md               # 본 실행 매뉴얼
```

---

## 2. 🖥️ 사전 전제조건 (Prerequisites)

### 1) 타겟 서버 요구사항
- **OS**: Linux (Ubuntu 22.04/24.04 LTS 권장, Debian, RHEL) 또는 Windows 10/11 (Docker Desktop + WSL2)
- **Docker Engine**: Docker 24.0+ 및 Docker Compose v2 (또는 `docker-compose` v2.20+)
- **디스크 공간**: 최소 **15 GB** 이상의 여유 디스크 공간 (DB 압축 덤프 및 볼륨 공간)
- **메모리(RAM)**: 최소 **16 GB** 권장 (vLLM/Qwen 모델 및 MySQL 8.0 버퍼)
- **GPU (선택/권장)**: NVIDIA GPU (VRAM 8GB+ 및 `nvidia-container-toolkit` 설치 시 vLLM GPU 가속 구동)

---

## 3. 🚀 마이그레이션 단계별 절차 (Step-by-Step)

### [1단계] 소스 서버에서 마스터 마이그레이션 팩 생성 (반복 실행 가능)
프로젝트 루트에서 **단일 명령어**를 실행하면 실시간 DB 덤프 추출, 소스코드 정제, 체크섬 발행, 단일 배포 아카이브(`dist/AISERVICE_Migration_Pack_*.zip` 또는 `.tar.gz`) 생성이 완전 자동화로 진행됩니다:

```bash
# Windows 소스 호스트 (원클릭 마스터 빌더)
.\make_migration_pack.bat

# Linux / macOS / WSL2 소스 호스트 (원클릭 마스터 빌더)
chmod +x make_migration_pack.sh
./make_migration_pack.sh

# 또는 Python 직접 실행
python make_migration_pack.py
```

- **옵션 안내**:
  - `--skip-dump`: DB 덤프는 기존 것을 재사용하고 소스코드/설정만 즉시 패키징할 때 사용
  - `--format <zip|tar.gz>`: 압축 포맷 선택
  - `--no-archive`: 단일 압축 파일 대신 `dist/AISERVICE_Migration_Pack/` 폴더 형태로 생성

---

### [2단계] 타겟 서버로 전송 (Transfer to Target Server)

`make_migration_pack` 실행 후 `dist/` 폴더에 생성된 압축 아카이브(또는 폴더)를 타겟 서버로 전송합니다.

```bash
# 단일 압축본 전송 예시 (SCP)
scp dist/AISERVICE_Migration_Pack_*.zip user@target-server-ip:/opt/
# 또는 Linux tar.gz 전송
scp dist/AISERVICE_Migration_Pack_*.tar.gz user@target-server-ip:/opt/
```

타겟 서버에서 압축을 해제합니다:
```bash
# Linux 타겟 서버에서 압축 해제
cd /opt
tar -xzvf AISERVICE_Migration_Pack_*.tar.gz
cd AISERVICE

# Windows 타겟 서버에서 압축 해제
Expand-Archive -Path .\dist\AISERVICE_Migration_Pack_*.zip -DestinationPath C:\
cd C:\AISERVICE
```

### [3단계] 타겟 서버에서 원클릭 복원 및 자동 부트스트랩

타겟 서버에서 아래의 **단일 명령어**를 실행하면 다음 작업이 완전 무인 자동화로 처리됩니다:
1. Docker 및 Compose 환경 검사
2. `checksums.sha256` 기반 데이터베이스 덤프 무결성 100% 검증
3. `.env` 환경 설정 파일 자동 프로비저닝
4. `pilos-db`, `bteam_db`, `redis` 컨테이너 선행 기동 및 MySQL 준비 대기
5. `pilos_v2`(3.4GB) 및 `oliview_project`(950MB) 덤프 스트리밍 무손실 복원
6. 10개 전 서비스 컨테이너 일괄 빌드 및 기동
7. 11개 엔드포인트 자동 헬스체크 검증 수행

```bash
# 타겟 서버가 Linux인 경우
cd /opt/aiservice/migration_pack
chmod +x scripts/*.sh
./scripts/bootstrap_restore.sh --force

# 타겟 서버가 Windows인 경우
cd C:\AISERVICE\migration_pack
.\scripts\bootstrap_restore.bat --force
```

---

## 4. 🧪 복원 완료 후 11개 엔드포인트 무결성 검증

복원 완료 후 언제든지 아래 검증기를 실행하여 모든 서비스가 정상 작동하는지 확인할 수 있습니다:

```bash
python migration_pack/scripts/verify_migration.py --json-report verification_report.json
```

### ✅ 11개 전수 검증 엔드포인트 목록
1. **통합 포털 게이트웨이**: `http://127.0.0.1:8080/` (HTTP 200)
2. **Model Gateway Health**: `http://127.0.0.1:8081/health` (HTTP 200)
3. **Model Gateway 카탈로그**: `http://127.0.0.1:8081/v1/models` (HTTP 200)
4. **Qwen LLM 추론**: `http://127.0.0.1:8081/v1/chat/completions` (HTTP 200, < 1s)
5. **BGE-M3 밀집 임베딩**: `http://127.0.0.1:8090/v1/embeddings` (1024차원 벡터 반환)
6. **A-Team Pilos 대시보드**: `http://127.0.0.1:8080/ateam/pilos/` (HTTP 200)
7. **A-Team Pilos API**: `http://127.0.0.1:8080/api/stocks` (HTTP 200)
8. **B-Team Oliview 프론트엔드**: `http://127.0.0.1:8080/bteam/oliview/` (HTTP 200)
9. **B-Team Oliview 백엔드**: `http://127.0.0.1:8080/bteam/oliview/api/health` (HTTP 200)
10. **B-Team 올리챗 A**: `http://127.0.0.1:8080/bteam/chata/` (HTTP 200)
11. **B-Team 올리뷰챗 B**: `http://127.0.0.1:8080/bteam/chatb/` (HTTP 200)

---

## 5. 🛠️ 트러블슈팅 가이드 (Troubleshooting)

### Q1. 타겟 서버에 포트 80 또는 8080이 이미 사용 중인 경우
타겟 서버의 `.env` 파일에서 `GATEWAY_PORT` 및 `GATEWAY_ALT_PORT`를 비어있는 포트로 변경합니다:
```ini
GATEWAY_PORT=8000
GATEWAY_ALT_PORT=8888
```
이후 `docker compose up -d gateway`를 실행하면 Nginx가 즉시 새 포트로 리바인딩됩니다.

### Q2. 타겟 서버에 NVIDIA GPU가 없는 CPU 전용 서버인 경우
`model_gateway` 컨테이너는 CPU 환경에서도 자동 폴백(Transformers/llama.cpp CPU 모드)을 지원합니다.
`docker-compose.yml`에서 `devices: [/dev/dxg]` 및 `NVIDIA_VISIBLE_DEVICES` 블록을 주석 처리하고 기동하시면 됩니다.

### Q3. 폐쇄망(인터넷 차단 환경)으로 이전하는 경우
소스 서버에서 `.\migration_pack\scripts\export_offline_models.bat`를 실행하여 모델 가중치를 `migration_pack/models/`에 번들링한 후 타겟 서버로 이전하십시오.
