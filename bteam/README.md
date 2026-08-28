# Oliview B-Team 통합 개발 및 실운영 전환 환경 (Blue / Green Cutover)

기존 `docker-compose.yml`과 원본 폴더는 **Blue** 기준선으로 유지됩니다. Feature 041의
Green은 코드·계약·공유 `packages/core`·uv workspace를 통합하여 독립 멀티 컨테이너로
구성되었으며, Feature 042를 통해 **무중단 실운영 컷오버(Zero-Downtime Cutover)** 및
**7일 롤백 안전망을 갖춘 아카이빙**을 지원합니다.

---

## 🚦 실운영 컷오버 및 전환 매뉴얼 (Feature 042 Production Cutover)

### 1. 거버넌스 승인 서명 검증 (Pre-Cutover Gate)
외부 변경 권한자(CAB)의 정식 승인 파일(`migration/approvals/cutover-approved.json`)의 4대 필수 필드 및 SHA-256 해시 체인을 검증합니다:

```bash
uv run python migration/verify_gate.py --gate CUTOVER_APPROVED
```

### 2. 백그라운드 15초 Graceful Drain 및 Fresh Backup
Blue 크롤링 파이프라인의 진행 중인 트랜잭션을 15초 내 완수(Drain)한 후 MySQL 일관된 스냅샷을 생성하여 `BACKUP_READY` 아티팩트를 발행합니다:

```bash
uv run python migration/execute_drain_backup.py
```

### 3. 최종 데이터 델타 동기화 및 랙 검증 (Delta Lag = 0)
MySQL과 Green ChromaDB v2(`oliview_review_sentences_v2`) 간의 랙 0을 확인하고 Redis 표적 무효화를 수행하여 `DATA_MIGRATION_READY` 아티팩트를 발행합니다:

```bash
uv run python migration/sync_final_delta.py
```

### 4. Nginx 게이트웨이 무중단 원자적 컷오버
`nginx -t` 구문 검사를 통과한 Green Candidate 설정으로 원자적 교체 및 `nginx -s reload`를 수행합니다:

```bash
# 구문 검사
uv run python deployment/nginx/switch_upstream.py --check

# Green 원자적 전환 적용
uv run python deployment/nginx/switch_upstream.py --apply
```

### 5. 전환 직후 Post-Cutover Smoke Test
4대 엔드포인트 및 20개 Zero-search 픽스처 대상 무환각/기권 응답을 즉시 검증합니다:

```bash
uv run pytest tests/integration/test_post_cutover_smoke.py -v
```

### 6. 24시간 안전 관찰(Soak Period) 모니터링 가동
30초 주기 프로브 및 4대 롤백 트리거(5xx 1건, 프로브 2연속 실패, SLA 2연속 초과, PII/환각 1건)를 상시 감시합니다:

```bash
uv run python deployment/monitor_soak.py --duration-hours 24 --interval-seconds 30
```

### 7. 비상 30초 긴급 롤백 절차
관찰 기간 중 이상 징후 발생 시 30초 이내에 Blue 레거시 업스트림으로 즉시 원복합니다:

```bash
uv run python deployment/nginx/switch_upstream.py --rollback
```

### 8. 24시간 Soak 통과 후 레거시 Blue 7일 보존 아카이빙
`DECOMMISSION_APPROVED` 승인 서명 검증 후 Blue 컨테이너를 중지하고 레거시 소스를 7일 보존 아카이브로 이전합니다 (DB 볼륨은 7일간 보존):

```bash
uv run python migration/archive_blue_stack.py --retention-days 7
```

---

## 🏗️ Green 멀티 컨테이너 로컬 실행

```bash
# secret 값을 출력하지 않는 topology 검사
docker compose -f docker-compose.green.yml config --no-interpolate

# Green 독립 멀티 컨테이너 빌드 및 구동
docker compose -p bteam-green -f docker-compose.green.yml up -d --build
```

- **대시보드 UI**: [http://localhost:15173](http://localhost:15173)
- **대시보드 API**: [http://localhost:15050](http://localhost:15050)
- **챗봇 A (Streamlit)**: [http://localhost:18501](http://localhost:18501)
- **챗봇 B (FastAPI RAG)**: [http://localhost:18002](http://localhost:18002)

---

## 🛑 서비스 종료 및 정리

```bash
# Green 컨테이너 중지
docker compose -p bteam-green -f docker-compose.green.yml down
```
