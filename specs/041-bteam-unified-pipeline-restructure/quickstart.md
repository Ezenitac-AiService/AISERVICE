# Quickstart: Oliview B-Team 통합 파이프라인 및 서비스 실행 가이드

**Feature**: `041-bteam-unified-pipeline-restructure`  
**Date**: 2026-08-27

---

## 1. 전주기 데이터 파이프라인 CLI 실행 (`pipeline_runner.py`)

### 전체 E2E 파이프라인 원클릭 실행 (크롤링 -> 문장분리 -> 감성분석 -> 보고서 -> 벡터인덱싱)
```powershell
Set-Location C:\AISERVICE\bteam
uv run python pipelines/pipeline_runner.py --product-id 12345 --steps all
```

`--product-id`는 내부 정수 PK이다. Olive Young `goodsNo`를 사용할 때는
`--product-code A000000189181`, 전체 제품일 때는 `--all-products`를 사용한다.

### 특정 단계별 독립 실행
```powershell
# 1. 크롤링만 실행
uv run python pipelines/pipeline_runner.py --product-code A000000189181 --steps crawl

# 2. 문장 분리 & 감성 분석만 실행
uv run python pipelines/pipeline_runner.py --product-code A000000189181 --steps sentence_split,sentiment

# 3. LLM 개선 제안 보고서 생성만 실행
uv run python pipelines/pipeline_runner.py --product-code A000000189181 --steps report

# 4. ChromaDB 증분 벡터 인덱싱만 실행
uv run python pipelines/pipeline_runner.py --product-code A000000189181 --steps index

# 5. 실패 단계부터 재개
uv run python pipelines/pipeline_runner.py --product-code A000000189181 --steps all --resume-run-id RUN_ID_FROM_FAILED_HISTORY

# 6. 6시간 주기 foreground 실행(제품·단계별 lock 적용)
uv run python pipelines/pipeline_runner.py --all-products --steps all --interval-hours 6
```

`--steps`는 `crawl,sentence_split,sentiment,report,index` 또는 단독 `all`만 허용한다. 빈 목록,
중복 단계, `all`과 다른 단계의 혼합, 음수 `--interval-hours`는 거부한다. 다중 단계는 입력
순서와 무관하게 `crawl -> sentence_split -> sentiment -> report -> index`의 고정 DAG 순서로
정규화한다. `--resume-run-id`는
지정한 `FAILED` 실행의 selector와 canonical steps가 현재 요청과 정확히 일치하고
`--interval-hours=0`일 때만 허용한다. DB 대량 쓰기 청크는 항상 500건이다.

`--all-products`는 `--interval-hours=0`인 단일 실행에서는 전체 catalog를 처리한다. 양수
interval의 각 cycle은 시작 시 immutable watermark를 기록한다. `crawl`은
`is_active=1 AND (review_checked_at IS NULL OR review_checked_at <= cycle_started_at - interval)`인
due product를 선택하고, 후속 단계는 각 단계의 성공 checkpoint 이후 생성·변경된 입력만
처리한다. cycle 전체가 성공한 뒤에만 watermark를 전진시킨다. 전체 catalog를 다시 처리하려면
interval을 0으로 둔 별도 단일 실행을 수행한다. runner는 foreground로 유지되며 Docker restart
policy 또는 외부 supervisor가 background 수명주기를 담당한다.

실제 `crawl` 단계는 `CRAWLER_ENDPOINT`를 통해 기존 크롤러 HTTP adapter를 주입해야
하며, `report` 단계는 `MODEL_GATEWAY_ENDPOINTS` JSON 배열을 요구한다. 기존 Compose
환경의 `GATEWAY_ENDPOINTS`는 호환 alias로 읽히지만, 필수 의존성이 없으면 runner는
성공 checkpoint를 만들지 않고 해당 단계에서 `FAILED`로 종료한다.

---

## 2. Blue를 유지한 Green 멀티 컨테이너 기동

> **안전 조건**: 아래 Green 구축·검증이 모두 끝날 때까지 현재 Blue 컨테이너와 외부 서비스는
> 계속 실행한다. 현재 `bteam/docker-compose.yml`, Blue network/volume 및 운영 Nginx upstream을
> 변경하지 않으며 `docker compose down`, volume 삭제, 레거시 폴더 삭제를 실행하지 않는다.
> Green의 MySQL/ChromaDB는 Blue snapshot을 별도 환경에 복구하고 Redis도 격리한다. startup
> preflight가 `DEPLOYMENT_STAGE=VALIDATION`에서 Green write endpoint와 Blue 운영 endpoint의
> 동일성을 발견하면 기동을 실패시킨다. `DEPLOYMENT_STAGE=CUTOVER` 진입은 전체 gate와 T048의
> `CUTOVER_APPROVED`, 첫 migration write는 `BACKUP_READY`, Nginx 전환은
> `DATA_MIGRATION_READY` artifact를 순서대로 요구한다. 네 artifact 형식과 이전 gate SHA-256
> hash chain은 `contracts/deployment_gate_contract.json`으로 검증한다.

```powershell
Set-Location C:\AISERVICE

# 1. 기존 Blue endpoint와 inventory/checksum이 정상인지 먼저 확인
# 2. 별도 project/network의 Green 멀티 컨테이너 기동
docker compose -f bteam/docker-compose.green.yml -p bteam-green up -d --build

# 3. Green 컨테이너별 상태 확인
docker compose -f bteam/docker-compose.green.yml -p bteam-green ps

# 4. 이미지 build context에 모델·SQL dump·ChromaDB가 포함되지 않았는지 확인
docker compose -f bteam/docker-compose.green.yml -p bteam-green build --progress=plain
```

Green은 단일 컨테이너가 아니다. 최소한 `pipeline_runner`, `dashboard_backend`,
`dashboard_frontend`, `chatbot_a`, `chatbot_b`가 각각 독립 컨테이너여야 하며, MySQL·Redis·
ChromaDB persistence·Model Gateway도 독립 의존 서비스로 유지한다. 고정 `container_name` 대신
Compose project와 color별 network alias로 Blue와 Green을 병행한다. Green은 Blue host port를
재사용하지 않고 내부 candidate network 또는 충돌 없는 `127.0.0.1` 검증 port만 사용한다.

---

## 3. 웹 서비스 및 게이트웨이 접속 확인

- **메인 프론트엔드 대시보드**: `https://ezenitac.duckdns.org/bteam/oliview/`
- **백엔드 REST API**: `https://ezenitac.duckdns.org/bteam/oliview/api/health`
- **ChatA (Streamlit)**: `https://ezenitac.duckdns.org/bteam/chata/`
- **ChatB (FastAPI)**: `https://ezenitac.duckdns.org/bteam/chatb/`

MySQL은 HTTP 200 대상이 아니며 Compose readiness probe로 확인한다. 위 URL은 Green 검증 중에도
Blue가 계속 제공한다. Green은 외부에 노출하지 않은 candidate route에서 네 HTTP 서비스,
pipeline runner, snapshot MySQL/ChromaDB, 격리 Redis와 Model Gateway readiness를 검증한다.

검색 0건, 인용 가능한 source review 부재 또는 기존 report의 citation 검증 실패 시에는 가짜 후기
대신 `NO_REVIEWS`, `NO_CITABLE_SOURCE`, `LEGACY_UNVERIFIED`, `GROUNDING_FAILED` 중 하나의
사유를 가진 abstention 응답이 반환되어야 한다. Green의 모든 grounded 리뷰 사실 주장은 v2
Chroma metadata와 report citation의 실존 `source_review_id`에 결속되어야 한다.

---

## 4. Quality Gate Command Matrix

모든 명령의 작업 디렉터리는 `C:\AISERVICE\bteam`이다. 각 명령은 exit code 0이어야 하며 원시
출력, 시작·종료 시각, commit/image digest와 환경 fingerprint를 artifact로 보존한다.

| Gate | Exact command |
| :--- | :--- |
| Workspace lock | `uv sync --frozen --all-packages` |
| Frontend install | `npm --prefix services/dashboard_frontend ci` |
| Frontend lint | `npm --prefix services/dashboard_frontend run lint` |
| Frontend build | `npm --prefix services/dashboard_frontend run build` |
| Unit | `uv run pytest tests/unit -q` |
| Contract | `uv run pytest tests/contract -q` |
| Characterization | `uv run pytest tests/characterization -q` |
| Integration/E2E | `uv run pytest tests/integration tests/test_e2e_pipeline.py -q` |
| Performance | `uv run pytest tests/performance -q -m performance` |
| Security | `uv run pytest tests/security -q -m security` |
| Lint | `uv run ruff check packages pipelines services tests` |
| Type check | `uv run mypy packages/core pipelines services` |
| Green Compose contract | `docker compose -f docker-compose.green.yml -p bteam-green config --quiet` |
| PRODUCTION override contract (승인 환경) | `docker compose -f docker-compose.green.yml -f docker-compose.production.yml -p bteam-green-prod config --quiet` |

성능 gate는 `tests/fixtures/performance_queries.jsonl` 첫 20개 query의 warm-up 결과를 제외한 뒤
전체 100개를 파일 순서대로 2회 실행한 200회 측정,
입력 256/output 512 token cap과 warm Redis/ChromaDB 상태를 사용한다. 로컬 단일 GTX 1070은
DEMO 판정에만 사용할 수 있다. PRODUCTION은 서로 다른 GPU instance의 Gateway endpoint 2개
이상과 Redis primary+replica+Sentinel quorum 또는 동등한 managed HA endpoint가 확인된 승인
환경에서만 실행·판정한다.

Frontend 명령은 `bteam/services/dashboard_frontend/package-lock.json`을 변경하지 않는
Node `^20.19.0 || >=22.12.0` 환경에서 실행한다. Python workspace는
`packages/core`, `pipelines`, `services/dashboard_backend`, `services/chatbot_a`,
`services/chatbot_b` 다섯 member이며 frontend는 uv workspace에 포함하지 않는다.

---

## 5. Cutover, Rollback 및 Blue 폐기 승인

1. 위 전체 gate, DB/ChromaDB 복구, PII·citation, Green readiness 결과를 외부 변경 권한자가 검토하고 `approved_by`, `approval_authority`, `approval_reference`가 있는 `bteam/migration/approvals/cutover-approved.json`(`CUTOVER_APPROVED`)을 발급한다. 구현 에이전트와 자동화는 이 승인 artifact를 만들거나 위조하지 않고 검증만 한다.
2. 승인 artifact 검증 후에만 Blue 사용자 HTTP 서비스를 유지한 채 background writer를 drain하고 fresh backup을 만든 뒤 `backup-ready.json`(`BACKUP_READY`)을 기록한다.
3. Blue와 호환되는 additive migration 및 checkpoint 기반 final delta sync를 수행한다. MySQL delta 0, Chroma v1/v2 lag 0, legacy Redis key class별 exact-target 또는 bypass/isolated policy 증거를 확인하고 `data-migration-ready.json`(`DATA_MIGRATION_READY`)을 기록한다. query/content-hash legacy key를 전역 scan/delete하지 않는다.
4. 세 artifact가 `contracts/deployment_gate_contract.json`의 hash chain과 rollback compatibility 조건을 통과한 뒤에만 candidate Nginx 설정에 `nginx -t`를 수행하고 upstream을 원자적으로 Green으로 전환·reload한다.
5. post-cutover smoke test를 실행하고 최소 24시간 Green-routed 외부 5xx, 30초 readiness, 5분 P95 window, PII·citation·데이터 정합성을 관찰한다. Blue는 계속 실행한다.
6. Green-routed 5xx 1건, probe 2회 연속 실패, P95 window 2회 연속 초과 또는 PII·무인용 claim·데이터 훼손 1건이 발생하면 즉시 사전 검증된 Blue rollback profile로 복귀하고 Green artifact를 보존한다. v1 dual-write가 끊겼거나 legacy cache citation을 검증할 수 없는 chatbot은 `ABSTENTION_FOR_UNVERIFIED`로 제한한다.
7. 24시간 soak와 Blue rollback rehearsal가 성공한 뒤 외부 변경 권한자가 `approved_by`, `approval_authority`, `approval_reference`가 있는 `decommission-approved.json`(`DECOMMISSION_APPROVED`)을 발급한다. 자동화는 이 승인을 생성하지 않는다.
8. 그 승인 artifact 검증 후에만 Blue 컨테이너를 중지하고 기존 원본 폴더·설정을 recoverable archive로 이동한다. 운영 volume과 snapshot은 기본적으로 삭제하지 않는다.
