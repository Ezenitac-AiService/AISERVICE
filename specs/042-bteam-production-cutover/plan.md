# Implementation Plan: Oliview B-Team 통합 아키텍처 실운영 전환 및 컷오버 (Production Cutover & Transition)

**Branch**: `042-bteam-production-cutover` | **Date**: 2026-08-28 | **Spec**: [spec.md](./spec.md)  
**Constitution Version**: v1.1.1 | **Compliance**: Quality-Gate Validation Required

---

## Summary

본 계획서는 피처 `041`을 통해 검증 완료된 B-Team Green 멀티 컨테이너 통합 스택으로 실제 운영 트래픽을 전환하는 **무중단 컷오버(Zero-Downtime Cutover), 최종 데이터 델타 동기화(Lag = 0), Nginx 게이트웨이 원자적 전환, 24시간 안전 관찰(Soak Period), 비상 롤백 메커니즘 및 7일 보존 기반 레거시 Blue Decommissioning**의 기술적 실행 방안을 정의합니다. 외부 변경 권한자 승인 서명 체계와 헌법 v1.1.1의 무환각/인라인 인용 결속 및 비파괴 원칙을 철저히 준수합니다.

---

## Technical Context

- **Language/Version**: Python 3.12 (uv workspace), Node.js `^20.19.0 || >=22.12.0` (React 19, Vite 8)
- **Primary Dependencies**: PyMySQL, SQLAlchemy, Alembic, ChromaDB, FastAPI, Streamlit, Flask, Redis, pydantic-settings, httpx
- **Gateway & Infrastructure**: Nginx (Reverse Proxy with `proxy_next_upstream` retry), Docker Compose (`bteam-green` project)
- **Storage**: MySQL 8.0 (`cosmetic_db`), ChromaDB (`oliview_review_sentences_v2`), Redis 7.x
- **Testing**: pytest (단위/계약/통합/보안/성능), ruff, mypy, Vite production build, Post-Cutover Smoke Test
- **Target Platform**: Windows / Linux Host, Nginx Reverse Proxy, Docker Compose
- **Performance Goals**: 읽기 트래픽 다운타임 0초, 백그라운드 드레인 $\le 15$초, 롤백 소요시간 $\le 30$초, DEMO 일반 RAG $\le 20.0$초, 상용 P95 $\le 5.0$초
- **Constraints**: 헌법 v1.1.1 준수, 4대 서명 필드 해시 체인 검증, 4대 이상 징후 감지 시 30초 내 즉각 롤백, 실증 환경 7일 롤백 자산 보존

---

## Constitution Check (v1.1.1)

- [X] **Principle I: 언어 및 커뮤니케이션 정책** - 모든 산출물, 계획서, 에러 메시지 및 소통을 한국어 표준으로 유지.
- [X] **Principle II: TDD 및 계약 검증** - 컷오버 및 전환 스크립트 작성 전 승인/경로/모니터링 계약 테스트를 선행 구축하고 검증.
- [X] **Principle III: 모듈화·격리·비파괴 보존** - Blue 스택을 24시간 상시 가동 대기 상태로 보존하고 7일간 데이터 볼륨을 안전 유지.
- [X] **Principle IV: 관측 가능성·구조화 로깅** - 24시간 Soak 모니터링 시계열 메트릭 기록 및 민감정보(비밀번호, PII) 평문 마스킹.
- [X] **Principle V: 단순성·점진적 진화 (YAGNI)** - 복잡한 추가 프록시 레이어 없이 표준 Nginx Symlink Swap 및 백오프 재시도 활용.
- [X] **Principle VI: 동적 운영 모드 및 100% 무환각/인용 결속** - `APP_RUN_MODE=DEMO`와 `PRODUCTION` 컷오버 게이트 분리 및 전환 후 100% 실존 리뷰 인라인 인용 무결성 유지.

---

## Project Structure & Target Files

```text
bteam/
├── migration/
│   ├── approvals/
│   │   ├── cutover-approved.json          # [EXTERNAL] 외부 CAB 승인 서명 아티팩트
│   │   └── decommission-approved.json     # [EXTERNAL] 외부 폐기 승인 서명 아티팩트
│   ├── artifacts/
│   │   ├── backup-ready.json              # [NEW] 백그라운드 드레인 및 MySQL 스냅샷 증거
│   │   ├── data-migration-ready.json      # [NEW] MySQL/Chroma v2 랙 0 동기화 증거
│   │   └── soak_metrics.jsonl             # [NEW] 24시간 관찰 기간 헬스체크 시계열 메트릭
│   ├── snapshots/                         # [NEW] 컷오버 직전 일관된 MySQL 스냅샷
│   ├── archive/                           # [NEW] 7일 롤백 보존 레거시 Blue 소스 아카이브
│   ├── verify_gate.py                     # [NEW] 승인 아티팩트 4대 필드 및 SHA-256 해시 체인 검증기
│   ├── execute_drain_backup.py            # [NEW] 15초 Graceful Drain 및 mysqldump 실행기
│   ├── sync_final_delta.py                # [NEW] Additive 마이그레이션 & Chroma v2 랙 0 검증기
│   └── archive_blue_stack.py              # [NEW] Blue 컨테이너 정지 및 7일 보존 아카이빙 스크립트
├── deployment/
│   ├── nginx/
│   │   ├── bteam.conf                     # [ACTIVE] 현재 활성 Nginx 라우팅 설정 (Symlink)
│   │   ├── bteam.candidate.conf           # [NEW] Green 멀티 컨테이너 업스트림 설정 (Candidate)
│   │   ├── bteam.rollback.conf            # [NEW] Blue 긴급 복구 업스트림 설정 (Rollback Profile)
│   │   └── switch_upstream.py             # [NEW] Nginx 원자적 심볼릭 링크 교체 및 reload 스크립트
│   └── monitor_soak.py                    # [NEW] 24시간 30초 주기 프로브 및 4대 트리거 롤백 감시 데몬
├── tests/
│   ├── contract/
│   │   ├── test_cutover_gate_contract.py  # [NEW] 4대 필드 해시 체인 및 게이트 검증 테스트
│   │   └── test_nginx_route_contract.py   # [NEW] Nginx candidate 및 retry 정책 계약 테스트
│   └── integration/
│       ├── test_post_cutover_smoke.py     # [NEW] 컷오버 직후 4개 엔드포인트 & Zero-search 스모크 테스트
│       └── test_soak_monitor_daemon.py    # [NEW] 이상 징후 시 30초 롤백 발동 시뮬레이션 테스트
└── README.md                              # [UPDATE] 실운영 전환 및 롤백 매뉴얼 갱신
```

---

## 단계별 구현 및 전환 로드맵

### Phase 1: 거버넌스 및 계약 검증 스위트 구축 (Contracts & Red Tests)
- `contracts/cutover_gate_contract.json`, `nginx_route_contract.json`, `soak_monitoring_contract.json`을 검증하는 계약 테스트 작성.
- 승인 파일 누락, 해시 불일치 시 fail-closed되는 방어 로직 단위 테스트 구현 (`test_cutover_gate_contract.py`).

### Phase 2: 데이터 델타 동기화 및 백업 파이프라인 (`migration/`)
- `PipelineActiveLease` 기반 15초 Graceful Drain 및 `mysqldump --single-transaction` 백업 스크립트(`execute_drain_backup.py`) 구현 $\rightarrow$ `BACKUP_READY` 발행.
- Alembic additive migration 및 ChromaDB v2(`oliview_review_sentences_v2`) 레코드 카운트 1:1 대조 스크립트(`sync_final_delta.py`) 구현 $\rightarrow$ `DATA_MIGRATION_READY` 발행.

### Phase 3: Nginx 게이트웨이 무중단 원자적 전환 (`deployment/nginx/`)
- `proxy_next_upstream` 3회 재시도 규칙이 포함된 `bteam.candidate.conf` 및 `bteam.rollback.conf` 작성.
- 원자적 Symlink 교체, `nginx -t` 구문 검사, `nginx -s reload` 스크립트(`switch_upstream.py`) 구현.
- 4개 서비스 및 20개 Zero-search 픽스처 대상의 Post-Cutover Smoke Test(`test_post_cutover_smoke.py`) 구축.

### Phase 4: 24시간 Soak 모니터링 자동화 및 30초 긴급 롤백 데몬 (`deployment/`)
- 30초 주기 프로브, 5분 윈도우 P95 지연시간 측정, 4대 롤백 트리거(5xx 1건, 프로브 2연속, SLA 2연속, PII/환각 1건) 실시간 감시 데몬(`monitor_soak.py`) 구현.
- 이상 징후 감지 시 30초 내 Blue 복구 업스트림으로 즉시 원복하는 자동 롤백 오케스트레이션 연결.

### Phase 5: 레거시 Blue 자산 7일 보존 아카이빙 (`migration/`)
- `DECOMMISSION_APPROVED` 승인 서명 검증기 및 Blue 컨테이너 graceful 중지 스크립트(`archive_blue_stack.py`) 구현.
- 레거시 소스 폴더의 시크릿 Redaction 및 `bteam/migration/archive/` 7일 보존 메타데이터 생성.

### Phase 6: 전체 시뮬레이션 리허설 및 품질 게이트 통과 (Verification)
- 전체 회귀 테스트, 컷오버 드라이런, 롤백 시뮬레이션, 정적 분석(Ruff/Mypy), Vite 번들 검증을 100% 통과.
