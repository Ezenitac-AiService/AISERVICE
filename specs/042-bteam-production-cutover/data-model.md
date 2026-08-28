# Data Model: B-Team Production Cutover & Transition

**Feature**: `042-bteam-production-cutover`  
**Date**: 2026-08-28

---

## 1. Entities & Schemas

### 1.1 CutoverApproval (운영 전환 승인 아티팩트)
외부 변경 권한자가 발급한 운영 전환 승인 메타데이터 파일 (`bteam/migration/approvals/cutover-approved.json`).

```json
{
  "gate_type": "CUTOVER_APPROVED",
  "approved_by": "lead-operator@ezenitac.com",
  "approval_authority": "Production Change Advisory Board",
  "approval_reference": "CAB-20260828-BTEAM-01",
  "approved_at": "2026-08-28T14:00:00Z",
  "target_environment": "DEMO",
  "previous_gate_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "signature_token": "sig_cab_prod_cutover_valid_token_hex"
}
```

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `gate_type` | string | Yes | 항상 `"CUTOVER_APPROVED"` |
| `approved_by` | string | Yes | 승인 발급자 식별자 |
| `approval_authority`| string | Yes | 승인 주체/조직명 |
| `approval_reference`| string | Yes | 변경 관리 티켓/참조 번호 |
| `approved_at` | string (ISO-8601 UTC) | Yes | 승인 일시 |
| `target_environment`| enum(`DEMO`, `PRODUCTION`) | Yes | 타겟 실행 환경 |
| `previous_gate_sha256`| string (Hex 64) | Yes | 직전 Preflight Gate 아티팩트의 SHA-256 해시 |
| `signature_token` | string | Yes | 권한 검증용 암호 서명 토큰 |

---

### 1.2 MigrationStateArtifact (전환 상태 전이 아티팩트)

#### A. BackupReady (`bteam/migration/artifacts/backup-ready.json`)
```json
{
  "gate_type": "BACKUP_READY",
  "created_at": "2026-08-28T14:05:00Z",
  "mysql_dump_path": "bteam/migration/snapshots/mysql_blue_pre_cutover.sql",
  "mysql_dump_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "row_counts": {
    "products": 246,
    "reviews": 15420,
    "llm_product_reports": 246
  },
  "in_flight_drain_seconds": 3.4,
  "previous_gate_sha256": "..."
}
```

#### B. DataMigrationReady (`bteam/migration/artifacts/data-migration-ready.json`)
```json
{
  "gate_type": "DATA_MIGRATION_READY",
  "created_at": "2026-08-28T14:10:00Z",
  "schema_migration_version": "041_bteam_additive_v2",
  "chroma_v2_collection": "oliview_review_sentences_v2",
  "chroma_v2_count": 48210,
  "chroma_lag_records": 0,
  "redis_invalidation_mode": "TARGETED_PRODUCT_KEYS_AND_BYPASS",
  "mysql_delta_lag_records": 0,
  "previous_gate_sha256": "..."
}
```

---

### 1.3 UpstreamRouteMap & Nginx Symlink State
Nginx 업스트림 매핑 엔티티 (`bteam/deployment/nginx/routes.json`).

| Route | Blue Target (Legacy) | Green Target (Unified) | Failover / Retry Policy |
| :--- | :--- | :--- | :--- |
| `/bteam/oliview/` | `127.0.0.1:5173` | `127.0.0.1:15173` | `proxy_next_upstream` 3회 |
| `/bteam/oliview/api/` | `127.0.0.1:5050` | `127.0.0.1:15050` | `proxy_next_upstream` 3회 |
| `/bteam/chata/` | `127.0.0.1:8501` | `127.0.0.1:18501` | `proxy_next_upstream` 3회 |
| `/bteam/chatb/` | `127.0.0.1:8002` | `127.0.0.1:18002` | `proxy_next_upstream` 3회 |

---

### 1.4 SoakHealthMetric & Rollback Trigger
24시간 관찰 기간 시계열 헬스 데이터 (`bteam/migration/artifacts/soak_metrics.jsonl`).

```json
{
  "timestamp": "2026-08-28T15:00:00Z",
  "probe_window_minutes": 5,
  "http_5xx_count": 0,
  "http_probe_success_rate": 1.0,
  "p95_latency_seconds": 1.42,
  "consecutive_probe_failures": 0,
  "pii_leakage_detected": false,
  "hallucination_detected": false,
  "rollback_triggered": false
}
```

---

### 1.5 DecommissionArchiveManifest (7일 롤백 보존 아카이브 메타데이터)
`bteam/migration/archive/blue_manifest.json`

```json
{
  "archive_id": "blue_archive_20260828_140000",
  "created_at": "2026-08-28T14:30:00Z",
  "retention_policy": "POC_DEMO_7_DAYS",
  "expires_at": "2026-09-04T14:30:00Z",
  "archived_paths": [
    "bteam/migration/archive/Oliview_Project",
    "bteam/migration/archive/Oliview_aspect_sentence_split",
    "bteam/migration/archive/Oliview_aspect_sentiment",
    "bteam/migration/archive/Oliview_LLM",
    "bteam/migration/archive/Oliview_chatbot_a",
    "bteam/migration/archive/Oliview_chatbot_b"
  ],
  "preserved_docker_volumes": [
    "bteam_mysql_data",
    "bteam_redis_data"
  ],
  "secrets_redacted": true
}
```
