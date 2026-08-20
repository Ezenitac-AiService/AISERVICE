# Quickstart Guide: 028-cross-platform-migration-pack

**Feature**: [spec.md](file:///c:/AISERVICE/specs/028-cross-platform-migration-pack/spec.md)  
**Date**: 2026-08-20  
**Status**: Completed  

---

## 1. 소스 호스트 (Source Server): 마이그레이션 팩 생성

현재 운영 중인 AISERVICE 서버에서 데이터베이스와 설정을 추출하여 마이그레이션 팩을 패키징합니다.

### 1.1 데이터베이스 덤프 및 무결성 체크섬 생성
```bash
# Windows
.\migration_pack\scripts\export_databases.bat

# Linux / WSL2
chmod +x migration_pack/scripts/*.sh
./migration_pack/scripts/export_databases.sh
```

- **결과 산출물**:
  - `migration_pack/database/pilos_v2.sql.gz` (~320MB)
  - `migration_pack/database/oliview_project.sql.gz` (~140MB)
  - `migration_pack/database/checksums.sha256`
  - `migration_pack/migration_manifest.json`

### 1.2 단일 아카이브 파일 생성 (선택 사항)
```bash
# Windows
.\migration_pack\scripts\pack_archive.bat

# Linux / WSL2
./migration_pack/scripts/pack_archive.sh
```
- 생성 파일: `aiservice_migration_pack_20260820.tar.gz` (또는 `.zip`)

---

## 2. 타겟 호스트로 팩 전송 (Transfer to Target Host)

SCP, Rsync, SFTP 또는 클라우드 스토리지(S3 등)를 통해 신규 서버로 전송합니다.

```bash
# 예시: SCP를 통한 타겟 서버 전송
scp -r ./migration_pack user@new-server-ip:/opt/aiservice/
# 또는 압축 파일 전송
scp aiservice_migration_pack_20260820.tar.gz user@new-server-ip:/opt/
```

---

## 3. 타겟 호스트 (Target Server): 원클릭 복원 및 기동

신규 서버(Ubuntu Linux, AWS EC2, 신규 Windows 등)에서 단일 부트스트랩 스크립트를 실행합니다.

### 3.1 원클릭 부트스트랩 실행
```bash
# 타겟 서버가 Linux인 경우
cd /opt/aiservice/migration_pack
chmod +x scripts/*.sh
./scripts/bootstrap_restore.sh --force

# 타겟 서버가 Windows인 경우
cd C:\AISERVICE\migration_pack
.\scripts\bootstrap_restore.bat --force
```

### 3.2 내부 자동 수행 시퀀스
1. 타겟 호스트 Docker & Compose 설치 여부 점검.
2. `migration_pack/config/.env.migration.template`을 기반으로 타겟 `.env` 자동 프로비저닝.
3. `pilos-db` 및 `bteam_db` 컨테이너 선행 기동 및 MySQL 헬스체크.
4. `pilos_v2` 및 `oliview_project` 덤프 스트리밍 복원.
5. 전체 서비스 컨테이너(10개) 일괄 빌드 및 기동.
6. 11개 엔드포인트 자동 E2E 회귀 헬스체크 실행.

---

## 4. 마이그레이션 무결성 최종 검증

```bash
# 수동 검증기 실행
python migration_pack/scripts/verify_migration.py --gateway-url http://localhost:80
```

- **성공 출력 예시**:
  ```text
  [PASS] Gateway Port 80 (HTTP 200) - 12ms
  [PASS] Gateway Port 8080 (HTTP 200) - 14ms
  [PASS] Model Gateway Health (HTTP 200) - 25ms
  [PASS] LLM Chat Completion (Qwen3.5-2B/4B) - 420ms
  [PASS] BGE-M3 Dense Embedding (1024-dim) - 85ms
  [PASS] BGE-Reranker-v2-m3 - 110ms
  [PASS] Pilos Web Dashboard (HTTP 200) - 30ms
  [PASS] Oliview Backend API (HTTP 200) - 18ms
  [PASS] Oliview Frontend (HTTP 200) - 22ms
  [PASS] Oliview Chatbot A Streamlit (HTTP 200) - 45ms
  [PASS] Oliview Chatbot B SSE Stream (HTTP 200) - 38ms
  [PASS] Database Integrity: pilos_v2 (11 tables OK), oliview_project (22 tables OK)
  ======================================================
  MIGRATION VERIFICATION: ALL 11 ENDPOINTS PASSED (100%)
  ======================================================
  ```
