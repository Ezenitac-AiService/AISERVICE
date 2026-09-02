# AISERVICE 우분투 서버 마이그레이션 운영 가이드 (v2.0)

본 문서는 Windows(WSL2) 환경에서 구축된 **AISERVICE 전체 인프라(도커 볼륨, DB, 실사용 `.env`, AI 모델 서빙 게이트웨이, DuckDNS DDNS)**를 **Ubuntu 24.04 LTS 서버(Intel i7-930, GTX 1070 8GB, 24GB RAM)**로 100% 무손실 이전하고 Zero-Config로 원클릭 복원하는 절차를 안내합니다.

---

## 1. 마이그레이션 아키텍처 개요

- **마이그레이션 모드**: `DEV_PLATFORM_TRANSFER` (개발 환경 1:1 완벽 보존 이전)
- **보안 및 환경설정**: 실사용 `.env` 및 `ddns/.env`의 모든 시크릿(DB 비밀번호, 키움 API 키, DuckDNS 토큰 등)을 암호화된 아카이브에 100% 보존하여 타겟 서버에서 사용자 수동 입력 0회(Zero-Config, 복호화 후 `chmod 600`)로 즉시 구동. 복호화 키는 아카이브 외부의 보호된 경로에서 주입.
- **타겟 하드웨어 프로파일**:
  - **CPU**: Intel Core i7-930 (Nehalem 1세대, SSE4.2 지원, Non-AVX) $\rightarrow$ `-march=native -DGGML_AVX=OFF` 자동 적용
  - **GPU**: NVIDIA GeForce GTX 1070 8GB (Pascal `sm_61`) $\rightarrow$ `CMAKE_CUDA_ARCHITECTURES=61`, `VRAM_SAFETY_LIMIT_MB=5000`
  - **RAM**: 24GB

---

## 2. 윈도우(개발 호스트) 패키징 실행

윈도우 개발 PC에서 터미널(PowerShell 또는 CMD)을 열고 아래 명령어를 실행하여 단일 배포 아카이브를 생성합니다:

```powershell
# 1. 사전 유효성 검사 (시뮬레이션)
python make_migration_pack.py --dry-run

# 2. 실데이터 및 볼륨 포함 전체 마이그레이션 팩 생성
python make_migration_pack.py --include-volumes --format tar.gz
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

## 3. 우분투 서버(타겟 호스트) 전송 및 복원

### 3.1 파일 전송 (SCP / SFTP / USB)
```bash
# 타겟 우분투 서버로 전송
scp dist/AISERVICE_Migration_Pack_*.tar.gz.enc user@ubuntu-server:/home/user/
```

### 3.2 원클릭 자동 복원 및 부트스트랩 실행
```bash
# 1. 타겟 호스트의 보호된 키 경로를 주입하고 승인된 복호화 절차로 .tar.gz를 준비
export MIGRATION_PACK_KEY_FILE=/etc/aiservice/migration-pack.key

# 2. 복호화된 아카이브 압축 해제
tar -xzf <DECRYPTED_ARCHIVE>
cd AISERVICE

# 3. 원클릭 부트스트랩 실행 (무인 자동 설치 모드)
sudo ./bootstrap_restore.sh -y
```

`bootstrap_restore.sh`가 아래 작업을 완전 자동(Zero-Touch)으로 수행합니다:
1. `chmod 600 .env` 보안 권한 적용 및 실행 스크립트 권한 부여
2. Clean Ubuntu 24.04 필수 패키지, 공식 APT Docker, NVIDIA Container Toolkit 자동 설치
3. WSL2 디바이스(`/dev/dxg`) 제거 및 Native Linux GPU Compose 자동 변환
4. i7-930 Non-AVX 및 GTX 1070 `sm_61` 하드웨어 감지 및 JIT 최적화 빌드
5. Docker Named Volume(`ateam_db_data`, `bteam_bteam_mysql_data`, `green_mysql_data`, `green_chroma_data`, `aiservice_redis_data`) 복원
6. Mutex 데이터베이스 중복 충돌 방지 및 안전 기동
7. DuckDNS DDNS IPv4(`curl -4`) 갱신 및 5분 주기 크론 자동 등록
8. 10개 HTTP + Redis TCP PING으로 구성된 11개 검사 수행 및 `verification_report.json` 발행

타겟 서버에서 아래의 **단일 명령어**를 실행하면 다음 작업이 완전 무인 자동화로 처리됩니다:
1. Docker 및 Compose 환경 검사
2. `checksums.sha256` 기반 데이터베이스 덤프 무결성 100% 검증
3. `.env` 환경 설정 파일 자동 프로비저닝
4. `pilos-db`, `bteam_db`, `redis` 컨테이너 선행 기동 및 MySQL 준비 대기
5. `pilos_v2`(3.4GB) 및 `oliview_project`(950MB) 덤프 스트리밍 무손실 복원
6. 10개 전 서비스 컨테이너 일괄 빌드 및 기동
7. 11개 엔드포인트 자동 헬스체크 검증 수행

```bash
python3 migration_pack/scripts/verify_migration.py
```

| 포트 | 서비스명 | 확인 URL | 비고 |
|:---|:---|:---|:---|
| **80** | Nginx 통합 게이트웨이 | `http://<서버IP>/` | 전체 포털 진입점 |
| **8080** | Nginx 보조 포트 게이트웨이 | `http://<서버IP>:8080/` | 보조 포털 진입점 |
| **8081** | Model Gateway (Qwen 2B) | `http://<서버IP>:8081/health` | LLM 추론 API |
| **8090** | BGE-M3 Dense Embedding | `http://<서버IP>:8090/v1/models` | 임베딩 API |
| **8091** | BGE-Reranker v2 | `http://<서버IP>:8091/v1/models` | 리랭커 API |
| **8080** | A-Team Pilos 대시보드 | `http://<서버IP>:8080/ateam/pilos/` | 감성지수 웹 |
| **8080** | B-Team Oliview 프론트 | `http://<서버IP>:8080/bteam/oliview/` | 화장품 랭킹 UI |
| **8080** | B-Team Oliview 백엔드 | `http://<서버IP>:8080/bteam/oliview/api/health` | API health |
| **8080** | B-Team 올리챗 A | `http://<서버IP>:8080/bteam/chata/` | Streamlit 챗봇 |
| **8080** | B-Team 올원챗 B | `http://<서버IP>:8080/bteam/chatb/` | FastAPI 챗봇 |
| **6379** | Redis 7 | TCP `localhost:6379` | PING/PONG 세션·캐시 검사 |

---

## 5. 트러블슈팅 가이드

1. **GPU 컨테이너 인식 실패 (`nvidia-smi` 오류)**:
   - `sudo systemctl restart docker` 실행 후 `sudo docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi`로 점검.
2. **DuckDNS 갱신 실패**:
   - `cat ddns/duckdns.log` 확인 및 수동 실행: `bash ddns/duck.sh`.
3. **i7-930 CPU 크래시 (`Illegal instruction`)**:
   - `python3 model_gateway/scripts/probe_hardware.py`로 `-DGGML_AVX=OFF` 플래그 확인 후 `bash model_gateway/scripts/build_llama.sh` 재실행.
