# Implementation Plan: Pilos 일별 문서 증분 집계 및 보고서 자동 갱신 동기화

**Branch**: `025-pilos-daily-doc-incremental-sync` | **Date**: 2026-08-20 | **Spec**: [`spec.md`](file:///c:/AISERVICE/specs/025-pilos-daily-doc-incremental-sync/spec.md)

## Summary

A-Team PILOS의 10분 주기 파이프라인에서 신규 수집된 댓글이 누락되지 않고 일별 문서(`daily_document`) 스냅샷으로 정상 누적 빌드되며, 최신 문서에 기반하여 Ridge AI 감성 추론과 LLM 시장 해설 보고서가 10분 주기 내에서 실시간으로 자동 갱신되도록 `daily_document_db.py` 쿼리 및 파이프라인 연계를 개선합니다.

---

## Technical Context

**Language/Version**: Python 3.12 (A-Team Pilos Container)  
**Primary Dependencies**: SQLAlchemy, Kiwi 형태소 분석기 (kiwipiepy), scikit-learn (Ridge 회귀), OpenAI SDK (vLLM 연결)  
**Storage**: MySQL 8.0 (`pilos_v2` 데이터베이스)  
**Testing**: Python unittest / pytest  
**Target Platform**: Linux Docker Container (`pilos-worker`, `pilos-web`, `pilos-db`)  
**Project Type**: Batch Pipeline & Web Service  
**Performance Goals**: 400만 건 이상의 댓글 테이블에서 대상 판정 쿼리 < 100ms, 10분 파이프라인 주기 내 7단계 완수 (< 120s)  
**Constraints**: 원장(`이주광.md`) 스냅샷 불변성 원칙 준수 (과거 daily_document 수정 없이 새 행 INSERT), 서비스 무중단 유지  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. 언어 및 커뮤니케이션 정책**: 모든 산출물(명세서, 계획서, 코드 주석 등) 한국어 작성 준수. (PASS)
- **II. TDD 및 테스트 우선주의**: 쿼리 수정 전 단위 테스트를 작성/검증하고 통합 파이프라인 검증 수행. (PASS)
- **III. 서비스 모듈화 및 격리**: A-Team Pilos 내부 모듈에 국한되며 B-Team 및 공통 인프라에 비파괴적 무결성 보존. (PASS)
- **IV. 관측 가능성 및 구조화된 로깅**: 파이프라인 실행 요약 및 일별 로그에 단계별 상태 정확히 기록. (PASS)
- **V. 단순성 및 점진적 진화 (YAGNI)**: 복잡한 프레임워크 추가 없이 기존 SQLAlchemy 쿼리 최적화로 가장 단순하게 해결. (PASS)

---

## Project Structure

### Documentation (this feature)

```text
specs/025-pilos-daily-doc-incremental-sync/
├── spec.md              # 기능 명세서
├── checklists/
│   └── requirements.md  # 요구사항 품질 체크리스트
├── plan.md              # 구현 계획서 (본 문서)
├── research.md          # 기술 연구 및 결정 사항
├── data-model.md        # 데이터 모델 및 스키마 관계
├── quickstart.md        # 실행 및 검증 가이드
└── contracts/
    └── pipeline-contracts.md  # 인터페이스 계약
```

### Source Code

```text
ateam/pilos-sentiment-index/
├── pilos/
│   ├── storage/
│   │   ├── daily_document_db.py       # [MODIFY] select_pending_daily_document_targets 쿼리 수정
│   │   └── inference_db.py            # [VERIFY] 최신 daily_document_id 조회 보장
│   ├── jobs/
│   │   ├── build_daily_documents.py   # [VERIFY] 일별 문서 빌드 작업
│   │   ├── predict_model.py           # [VERIFY] Ridge 추론 작업
│   │   ├── generate_llm_reports.py    # [VERIFY] LLM 보고서 갱신 작업
│   │   └── worker_daemon.py           # [VERIFY] 10분 주기 데몬 루프
│   └── service/
│       └── sentiment_index_service.py # [VERIFY] 대시보드 최신 적재 정보 조회
└── tests/
    └── test_daily_document_db.py      # [NEW/MODIFY] 증분 타겟 조회 및 스냅샷 생성 단위 테스트
```

---

## Implementation Steps

1. **테스트 코드 작성/보강**:
   - `tests/test_daily_document_db.py`에 기존 daily_document가 존재하는 상황에서 미매핑 tokenized_comment가 추가되었을 때 타겟으로 정상 반환되는지 검증하는 단위 테스트 작성.
2. **`daily_document_db.py` 쿼리 수정**:
   - `select_pending_daily_document_targets`에서 `NOT EXISTS (SELECT 1 FROM daily_document ...)` 블록 제거.
   - `idx_daily_document_comment_tokenized` 인덱스를 타도록 `NOT EXISTS (SELECT 1 FROM daily_document_comment ddc WHERE ddc.tokenized_comment_id = tc.tokenized_comment_id)` 최적화.
3. **단위 테스트 및 파이프라인 검증**:
   - `docker exec pilos-worker python -m unittest tests/test_daily_document_db.py` 실행.
   - `run_service_pipeline`을 1회 실행하여 8월 19일치 35,999건 및 8월 20일 새벽 데이터가 즉시 일별 문서와 보고서로 동기화되는지 검증.
4. **결과 확인 및 대시보드 검증**:
   - MySQL 적재 건수 및 웹 UI 화면 반영 확인.
