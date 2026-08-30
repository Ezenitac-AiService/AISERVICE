# Quickstart Validation Guide: 043-docker-volume-ubuntu-migration-pack

**Feature**: `043-docker-volume-ubuntu-migration-pack`  
**Purpose**: Windows 개발 환경에서 마이그레이션 팩을 패키징하고 타겟 Ubuntu 24.04 LTS 서버에서 원클릭으로 복원 및 10개 HTTP + Redis TCP PING 11개 검사를 검증하는 전주기 실행 매뉴얼

---

## 1. 소스 환경 (Windows 11) 패키징 절차

### 1.1 사전 검증 모드 (Dry-Run)
대용량 압축 전 DB 연결 상태, 볼륨 크기, 디스크 공간을 5초 이내에 사전 점검합니다:
```powershell
python make_migration_pack.py --dry-run
```
Green 스택까지 포함하는 기능이므로 `.env`에 다음 네 항목을 실제 값으로 미리 설정해야 하며, 누락 시 dry-run이 실패합니다(비밀번호는 문서나 매니페스트에 기록하지 않습니다):
```text
GREEN_DB_NAME=cosmetic_db
GREEN_DB_USER=bteam_green
GREEN_DB_PASSWORD=<protected-value>
GREEN_DB_ROOT_PASSWORD=<protected-value>
```

### 1.2 마이그레이션 팩 생성
Docker 볼륨 및 실사용 `.env`가 암호화된 상태로 포함된 단일 아카이브를 생성합니다. 기본 형식은 `.tar.gz`이며, 필요하면 `.zip` 또는 두 형식을 선택합니다:
```powershell
python make_migration_pack.py --include-volumes --format tar.gz --target-os ubuntu --target-cpu i7-930 --target-gpu gtx1070
```
- **출력물**: `dist/AISERVICE_Migration_Pack_<TIMESTAMP>.tar.gz.enc` 및 `dist/checksums.sha256` (`--format zip`은 `.zip.enc`, `--format both`는 두 형식 생성)
- **보안**: 복호화 키는 아카이브에 포함하지 않으며, 매니페스트·로그·체크섬에는 시크릿 원문을 기록하지 않습니다.

### 1.3 타겟 우분투 서버로 전송 (SCP)
```powershell
scp dist/AISERVICE_Migration_Pack_*.tar.gz.enc ubuntu@<TARGET_UBUNTU_IP>:~/
```

---

## 2. 타겟 환경 (Ubuntu 24.04 LTS) 원클릭 복원 및 기동

### 2.1 아카이브 복호화 및 압축 해제
타겟 호스트의 보호된 키 경로를 `MIGRATION_PACK_KEY_FILE`로 주입하고 번들 provider의 버전 고정 envelope로 배포 아카이브를 복호화합니다. 키가 없으면 복원을 진행하지 않습니다.
```bash
export MIGRATION_PACK_KEY_FILE=/etc/aiservice/migration-pack.key
python3 migration_pack/scripts/bootstrap_restore.py \
  --archive <ENCRYPTED_ARCHIVE> --extract-to . --key-file "$MIGRATION_PACK_KEY_FILE"
```

```bash
cd AISERVICE
```

### 2.2 원클릭 자동 부트스트랩 (무인 배포)
단일 명령어로 OS 인프라 프로비저닝, 볼륨 복원, DuckDNS 동기화, 서비스 기동, 헬스체크까지 완수합니다:
```bash
sudo ./bootstrap_restore.sh -y
```

스크립트 내부 자동 수행 항목:
1. `chmod 600 .env` 보안 권한 및 스크립트 실행 권한 부여
2. Docker Engine 및 NVIDIA Container Toolkit 자동 설치 (미설치 시)
3. Compose 파일 WSL2 경로(`/dev/dxg`) $\rightarrow$ Native Linux GPU 런타임 정규화
4. 기본/Green MySQL DB 덤프 및 Docker 볼륨(MySQL/ChromaDB/Redis) 무손실 복원
5. DuckDNS IPv4 즉시 갱신 및 5분 주기 크론 등록
6. i7-930(Non-AVX) / GTX 1070(`sm_61`) 타겟 `llama.cpp` JIT 컴파일 및 모델 로드
7. 멀티 컨테이너 순차 기동 및 E2E 헬스체크 게이트 통과

---

## 3. 마이그레이션 결과 무결성 검증

### 3.1 11개 전수 검사(10개 HTTP + Redis TCP PING)
```bash
python3 migration_pack/scripts/verify_migration.py
```

### 3.2 검증 대상 엔드포인트 목록
1. `GET http://localhost/` $\rightarrow$ Nginx 통합 포털 (HTTP 200)
2. `GET http://localhost:8080/` $\rightarrow$ Nginx 보조 포트 포털 (HTTP 200)
3. `GET http://localhost:8081/health` $\rightarrow$ Model Gateway Qwen 2B LLM (HTTP 200)
4. `GET http://localhost:8090/health` $\rightarrow$ BGE-M3 Dense 임베딩 서비스 (HTTP 200)
5. `GET http://localhost:8091/health` $\rightarrow$ BGE-Reranker-v2-m3 리랭킹 서비스 (HTTP 200)
6. `GET http://localhost/ateam/pilos/` $\rightarrow$ A-Team Pilos 주식 감정지수 대시보드 (HTTP 200)
7. `GET http://localhost/bteam/oliview/` $\rightarrow$ B-Team Oliview 화장품 프론트엔드 (HTTP 200)
8. `GET http://localhost/bteam/oliview/api/health` $\rightarrow$ B-Team Oliview 백엔드 API (HTTP 200)
9. `GET http://localhost/bteam/chata/` $\rightarrow$ B-Team 올리챗 (Streamlit) (HTTP 200)
10. `GET http://localhost/bteam/chatb/` $\rightarrow$ B-Team 올원챗 (FastAPI) (HTTP 200)
11. `redis-cli -h localhost -p 6379 PING` $\rightarrow$ Redis 세션/캐시 인프라 (PONG)

### 3.3 검증 성공 판정
`verification_report.json`에서 `status: "PASS"` 및 `passed_endpoints: 11 / 11`을 확인합니다. HTTP 10개는 200 OK, Redis 검사는 PING/PONG을 만족해야 합니다.

### 3.4 SLA 및 호환성 검증
- 사전 인프라 준비 서버: 부트스트랩 시작부터 전 서비스 기동까지 10분 이내
- 완전 클린 Ubuntu: 드라이버·Docker 설치를 포함해 25분 이내
- 동일한 팩을 Ubuntu 22.04와 24.04에서 실행하여 CRLF, 권한, Docker/GPU 런타임 오류가 없는지 확인
