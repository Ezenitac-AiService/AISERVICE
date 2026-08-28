# Quickstart & Run Guide: B-Team Production Cutover

**Feature**: `042-bteam-production-cutover`  
**Date**: 2026-08-28

---

## 1. 사전 준비 및 승인 아티팩트 투입 (Pre-Cutover Stage)

### 1.1 외부 변경 권한자 승인 서명 파일 배치
외부 변경 관리 위원회(CAB)에서 발급한 `cutover-approved.json`을 `bteam/migration/approvals/` 경로에 배치합니다.

```powershell
Set-Location C:\AISERVICE\bteam

# 1. 승인 파일 존재 및 SHA-256 해시 체인 검증
uv run python migration/verify_gate.py --gate CUTOVER_APPROVED
```

---

## 2. 최종 델타 동기화 및 백업 (Final Delta Sync Stage)

### 2.1 백그라운드 15초 Graceful Drain & Fresh Backup
```powershell
# 1. Blue 백그라운드 크롤러 Graceful Drain 및 MySQL 백업 (BACKUP_READY 아티팩트 생성)
uv run python migration/execute_drain_backup.py

# 2. Additive 마이그레이션 및 ChromaDB v2 랙 0 동기증분 검증 (DATA_MIGRATION_READY 아티팩트 생성)
uv run python migration/sync_final_delta.py
```

---

## 3. Nginx 업스트림 원자적 컷오버 (Atomic Cutover Stage)

### 3.1 Nginx 구문 검증 및 설정 리로드
```powershell
# 1. Candidate Nginx 설정 구문 검사
uv run python deployment/nginx/switch_upstream.py --check

# 2. Green 업스트림으로 원자적 심볼릭 링크 교체 및 무중단 리로드
uv run python deployment/nginx/switch_upstream.py --apply
```

### 3.2 컷오버 직후 Post-Cutover Smoke Test
```powershell
# 4개 엔드포인트 및 20개 Zero-search 픽스처 즉시 검증 (5xx 0건, 인용 무결성 확인)
uv run python tests/integration/test_post_cutover_smoke.py
```

---

## 4. 24시간 Soak 모니터링 가동 (24h Soak Monitoring)

```powershell
# 30초 주기 헬스체크 및 4대 롤백 트리거 상시 감시 데몬 실행
uv run python deployment/monitor_soak.py --duration-hours 24 --interval-seconds 30
```

---

## 5. 긴급 비상 롤백 절차 (Emergency 30s Rollback)

관찰 기간 중 5xx 발생, SLA 초과, 프로브 실패 감지 시 단일 명령으로 30초 내 Blue 복귀:

```powershell
# Nginx 설정을 즉각 Blue로 원복하고 캐시 바이패스 프로파일 적용
uv run python deployment/nginx/switch_upstream.py --rollback
```

---

## 6. 24시간 Soak 완료 후 레거시 폐기 및 7일 보존 아카이빙 (Decommission Stage)

```powershell
# 1. 외부 DECOMMISSION_APPROVED 승인 서명 검증
uv run python migration/verify_gate.py --gate DECOMMISSION_APPROVED

# 2. Blue 컨테이너 graceful 정지 및 소스 코드 7일 보존 아카이브 이동 (DB 볼륨은 7일간 보존)
uv run python migration/archive_blue_stack.py --retention-days 7
```
