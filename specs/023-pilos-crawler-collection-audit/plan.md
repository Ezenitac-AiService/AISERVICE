# Implementation Plan: A-Team Pilos 댓글 크롤러 로직 전면 재점검 및 18~19일 결손 정합성 복원

**Branch**: `023-pilos-crawler-collection-audit` | **Date**: 2026-08-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/023-pilos-crawler-collection-audit/spec.md`

---

## Summary

`pilos.collection.comment_crawler`의 불필요한 메타데이터 필터링 결함을 제거하여 대댓글 및 비정형 작성자 댓글의 100% 수집 무결성을 확보하고, 2026-08-18 00:00(KST)까지의 10개 전 종목 일괄 소급 백필과 7단계 서비스 파이프라인(전처리 -> 토큰화 -> 일별문서 -> 수급 -> Ridge -> LLM 리포트)의 연속 실행을 통해 18일~19일 결손 데이터를 완전 복원한다.

---

## Technical Context

**Language/Version**: Python 3.12 (uv package manager)
**Primary Dependencies**: `requests`, `pymysql`, `kiwipiepy`, `scikit-learn`, `openai` (vLLM), `pydantic`
**Storage**: MySQL 8.0 (`pilos_v2` database), Date-partitioned JSONL files (`data/raw/`)
**Testing**: `unittest` test harness in `pilos/collection/test` and `tests/`
**Target Platform**: Linux Docker containers (`pilos-web`, `pilos-worker`, `pilos-db`) & Windows local environment
**Performance Goals**: 10개 종목 소급 백필 < 180초, 단일 페이지 요청 0.5s ± 0.2s 지터, HTTP 429 0회 차단
**Constraints**: Append-only 원본 JSONL 보존, DB `INSERT IGNORE` 0% 중복 충돌, 비식별화 솔트 해싱 100% 연속성 유지

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **Principle 1 (TDD & Verification)**: PASS - 크롤러 파싱 및 비식별화 단위 테스트 사전 정의
- **Principle 2 (Service Isolation)**: PASS - A팀 Pilos 디렉토리 및 `pilos-db` 내에서만 격리 실행
- **Principle 3 (Observability & Structured Logs)**: PASS - 종목별 수집 건수 및 경계 커서 매니페스트/DB 기록
- **Principle 4 (Append-Only & Data Integrity)**: PASS - 원본 JSONL 및 `preprocessed_comment` 무결성 보존
- **Principle 5 (Clear Documentation in Korean)**: PASS - 모든 기술 명세 및 계획 한국어 기술

---

## Project Structure

### Documentation (this feature)
```text
specs/023-pilos-crawler-collection-audit/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (This file)
├── research.md          # Technical research & decisions
├── data-model.md        # Core entities & lifecycle
├── quickstart.md        # Verification run guide
├── contracts/
│   └── crawler_contracts.md # Interfaces & cascade contracts
└── checklists/
    └── requirements.md  # Quality checklist
```

### Source Code Touched
```text
ateam/pilos-sentiment-index/
├── pilos/
│   ├── collection/
│   │   ├── comment_crawler.py      # [MODIFY] _select_page 필터링 결함 수정 & 대댓글 평탄화
│   │   ├── constants.py            # [MODIFY] BASE_TIME 0.5s 지터 튜닝
│   │   └── data_masking.py         # [MODIFY] ANONYMOUS_USER / 익명 fallback 안전 처리
│   ├── jobs/
│   │   ├── backfill_comments.py    # [MODIFY] 10개 전 종목 일괄 소급 백필 CLI 강화
│   │   └── run_service_pipeline.py # [MODIFY] 백필 후 7단계 엔드투엔드 연쇄 트리거 지원
│   └── storage/
│       └── comment_store.py        # [MODIFY] 대댓글 평탄화 레코드 라우팅 점검
└── tests/
    └── collection/
        └── test_crawler_audit.py   # [NEW] 결손 수정 검증 단위 테스트
```

---

## Implementation Phases

### Phase 1: Crawler Parsing & De-identification Defect Fix
1. `pilos/collection/comment_crawler.py`: `_select_page()`에서 `profile_id`, `nickname`이 없어도 `last_cursor`를 정상 갱신하고 레코드를 유지하도록 수정.
2. `pilos/collection/data_masking.py`: `None` 값 입력 시 `"ANONYMOUS_USER"`, `"익명"`으로 자동 치환하여 SHA-256 해시 생성.
3. `pilos/collection/comment_crawler.py`: 대댓글/답글(`replies`, `subComments`) 평탄화 추가.

### Phase 2: Backfill Engine & Cascade Automation
1. `pilos/jobs/backfill_comments.py`: `--target all` 옵션 추가 및 10개 전 종목 18일 00:00(KST)까지 일괄 소급 백필 지원.
2. `pilos/jobs/run_service_pipeline.py`: 백필 완료 후 `run_service_pipeline()` 호출로 Kiwi 토큰화 -> 일별문서 -> Ridge 추론 -> LLM 보고서 연쇄 갱신.

### Phase 3: Live Verification & Data Audit
1. `docker compose exec pilos_worker`를 통해 18~19일 소급 백필 실행.
2. MySQL `pilos_v2.preprocessed_comment` 건수 확인 (18일 2.6만+, 19일 3.5만+ 건 정상 복원).
3. 10개 전 종목의 웹 대시보드 리포트 생성 및 감성 지표 복원 검증.
