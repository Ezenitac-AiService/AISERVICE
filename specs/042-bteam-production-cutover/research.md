# Research & Technical Decisions: B-Team Production Cutover & Transition

**Feature**: `042-bteam-production-cutover`  
**Date**: 2026-08-28  
**Status**: Completed & Approved

---

## 1. Nginx Upstream Switching & Zero-Downtime Traffic Redirection

### Decision
Nginx 리버스 프록시의 활성 설정을 candidate 설정으로 원자적 심볼릭 링크(Symlink Swap) 교체하고 `nginx -s reload`를 수행하며, Upstream 블록에 `proxy_next_upstream error timeout http_502 http_503;` 및 `proxy_next_upstream_tries 3;`을 강제 설정한다.

### Rationale
- `nginx -s reload`는 기존 마스터 프로세스가 새 설정으로 신규 워커를 띄우고, 구 워커는 in-flight 연결을 완수한 후 graceful shutdown하므로 TCP 레벨에서 연결 단절이 발생하지 않는다.
- 전환 순간 극히 드문 race condition으로 인한 일시적 커넥션 거절이 발생하더라도 `proxy_next_upstream` 3회 재시도를 통해 클라이언트(외부 사용자)에게는 100% 투명하게 200 OK를 보장한다.

### Alternatives Considered
- **DNS 레벨 전환 (A/CNAME 레코드 변경)**: DNS TTL 캐싱으로 인해 전 세계/로컬 캐시에 갱신 지연(수 분~수 시간)이 발생하고 Blue/Green 트래픽이 통제 불가능하게 혼재되어 기각됨.
- **Port Proxy / HAProxy 이중화 레이어 추가**: 현재 단일 호스트 인프라에 불필요한 계층 복잡성(YAGNI 위반)을 유발하므로 표준 Nginx Symlink Swap 채택.

---

## 2. In-Flight Background Drain & Final Delta Synchronization

### Decision
Blue의 백그라운드 크롤링/인덱싱 파이프라인 정지 시 `PipelineActiveLease` 기반의 15초 Graceful Drain(현재 처리 중인 단일 500건 배치 커밋 완수 후 즉시 종료)을 적용하고, `mysqldump --single-transaction`으로 일관된 스냅샷을 생성하여 `BACKUP_READY`를 발행한 뒤, ChromaDB v2 레코드 수와 MySQL `reviews.sentiment_analyzed_at` 건수를 대조하여 랙(Lag) 0을 확인한다.

### Rationale
- 진행 중인 트랜잭션을 강제 SIGKILL하면 MySQL 롤백 및 파이프라인 이력 불일치가 발생하므로 최대 15초의 1 청크 완수 유예가 필수적이다.
- 웹/API/챗봇의 읽기 트래픽은 0초 중단으로 계속 서빙되므로 비즈니스 영향이 없다.
- ChromaDB v2(`oliview_review_sentences_v2`)의 총 벡터 개수와 MySQL 분석 완료 리뷰 건수의 1:1 정량 검증을 통해 유실 없는 `DATA_MIGRATION_READY`를 보장한다.

### Alternatives Considered
- **실시간 Dual-Write 영구 유지**: Blue와 Green 간 스키마 차이로 인한 코드 복잡도가 과도하고, 컷오버 시점의 순간 락 문제를 해결하기 어려워 15초 Drain 기반 Final Delta Sync 채택.

---

## 3. Redis Versioned Cache Targeted Invalidation & Bypass

### Decision
상품 식별자가 확정된 키(`bteam:DEMO:product:{id}:report:v*`, `bteam:DEMO:product:{id}:rag:v*`)만 표적으로 정밀 삭제하고, 해시 기반 임베딩/리랭킹 캐시는 flush하지 않은 채 Green의 신규 네임스페이스(`bteam:DEMO:product:*`)를 독립 퍼블리시한다. 롤백 시에는 사전 검증된 cache-bypass 프로파일을 적용한다.

### Rationale
- `FLUSHDB` 또는 wildcard `KEYS *` 삭제는 프로덕션 Redis 인스턴스의 일시적 블로킹(Stop-the-world)을 유발하고 A-Team 등 타 서비스 캐시를 오염시킬 수 있다.
- Green은 자체 버전 네임스페이스를 사용하므로 레거시 캐시와 키 충돌이 0%이다.

---

## 4. 4-Field Cryptographic Governance Gate (`CUTOVER_APPROVED`)

### Decision
승인 파일(`bteam/migration/approvals/cutover-approved.json`)은 다음 4대 필수 필드를 엄격히 요구한다:
1. `approved_by` (승인자 이메일/ID)
2. `approval_authority` (승인 권한/조직)
3. `approval_reference` (티켓/변경 승인 번호)
4. `previous_gate_sha256` (직전 `preflight-gate.json`의 SHA-256 해시)

자동화 스크립트는 이 파일의 무결성과 해시 체인을 검증만 하며, 자체 생성하지 않는다.

### Rationale
- 자동화 파이프라인이나 AI 에이전트가 승인 아티팩트를 임의 생성(Hallucinate/Bypass)하는 보안 사고를 원천 차단(Fail-Closed)한다.

---

## 5. 24-Hour Soak Automation & 30-Second Rapid Rollback

### Decision
컷오버 후 24시간 동안 백그라운드 모니터링 데몬이 30초 주기로 4개 서비스(`dashboard_frontend`, `dashboard_backend`, `chatbot_a`, `chatbot_b`) 및 Zero-search 픽스처를 프로브하고, 4대 임계치(5xx 1건, 프로브 2연속 실패, P95 SLA 2연속 초과, PII/환각 1건) 충족 시 30초 이내에 Nginx 심볼릭 링크를 Blue로 원복(`nginx -s reload`)한다.

### Rationale
- 자동화된 신속 롤백 트리거가 존재해야만 야간이나 주말에도 상용 서비스 장애 위험을 0으로 통제할 수 있다.

---

## 6. 7-Day Retention Decommissioning for PoC/DEMO Environment

### Decision
24시간 Soak 통과 및 `DECOMMISSION_APPROVED` 승인 후 Blue 컨테이너를 중지하고 소스 코드는 `bteam/migration/archive/blue_YYYYMMDD_HHMMSS/`로 이동하되, `.env` 및 시크릿 값은 redaction한다. Docker 볼륨(`bteam_mysql_data`, `bteam_redis_data`) 및 백업 스냅샷은 7일 동안 보존하고 7일 만료 후 안전하게 정리(Cleanup)할 수 있는 가이드를 제공한다.

### Rationale
- 실증/테스트 서버의 디스크 리소스를 절약하면서도, 예상치 못한 과거 데이터 대조 및 비상 원복을 위한 충분한 7일 유예 기간을 확보한다.
