# Implementation Plan: 012-restore-pilos-pipeline

**Branch**: `012-restore-pilos-pipeline` | **Date**: 2026-08-19 | **Spec**: [`spec.md`](file:///c:/AISERVICE/specs/012-restore-pilos-pipeline/spec.md)

**Input**: Feature specification from [`specs/012-restore-pilos-pipeline/spec.md`](file:///c:/AISERVICE/specs/012-restore-pilos-pipeline/spec.md)

---

## Summary

Pilos 주식 분석 파이프라인의 5단계(수급 데이터 수집)에서 발생하던 키움 API Key 미설정 예외(`ValueError`)를 결함 허용(Graceful Fallback / `JobStatus.SKIPPED`) 방식으로 개선하여 파이프라인 연쇄 중단을 원천 차단합니다. 또한 GPU VRAM을 4GB 이하로 쾌적하게 유지하기 위해 기본 LLM 서빙 모델을 경량 모델(`qwen3.5-2b`)로 최적화하고, 8월 12일부터 현재(8월 19일)까지 누락된 감성 지수 분석 및 AI 시장 해설 보고서를 10개 전 종목에 대해 100% 전수 소급 생성(Backfill)합니다.

---

## Technical Context

- **Language/Version**: Python 3.11 / Python 3.12 (A-Team Pilos, vLLM Server Gateway)
- **Primary Dependencies**: FastAPI, Flask, SQLAlchemy, Kiwi (Korean Morphological Tokenizer), scikit-learn (Ridge Regression), llama-cpp-python / vLLM Gateway
- **Storage**: MySQL 8.0 (`pilos_v2` database: `comments`, `preprocessed_comment`, `tokenized_comment`, `daily_document`, `sentiment_index_result`, `llm_report`, `service_pipeline_run`)
- **Testing**: pytest (단위 및 통합 회귀 테스트 스위트)
- **Target Platform**: Docker 컨테이너 인프라 (NVIDIA GPU 가속, WSL2 / Linux 환경)
- **Project Type**: AI 데이터 파이프라인, 모델 서빙 게이트웨이 및 금융 분석 웹 서비스
- **Performance Goals**: 10분 주기 백그라운드 파이프라인 100% 무중단 완수, LLM 보고서 1건당 생성 시간 < 5초
- **Constraints**: GPU VRAM 점유량 < 4.0GB 유지, 단일 종목 실패 시 타 종목 영향 없는 격리(Fault Isolation)
- **Scale/Scope**: KOSPI 대표 10개 종목, 8월 12일~19일 누락 거래일 전수 소급

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. 언어 및 커뮤니케이션 정책 (Korean/English Dual Policy)**: 모든 대화 및 산출물(명세서, 계획서, 작업목록, 코드 주석)을 한국어로 작성하고, 내부 추론은 영어로 수행함.
- [x] **II. TDD 및 테스트 우선주의 (Test-First & Contract Verification)**: 수급 수집 Fallback 및 파이프라인 상태 처리 단위 테스트를 선행 검증함.
- [x] **III. 서비스 모듈화 및 격리 (Service Modularity & Environment Isolation)**: A-Team Pilos 및 Model Gateway 내부에서만 수정하며 B-Team 소스코드 및 외부 런타임을 절대 훼손하지 않음.
- [x] **IV. 관측 가능성 및 구조화된 로깅 (Observability & Structured Logging)**: 파이프라인 7단계별 상태, 소요 시간, 실패 사유를 구조화된 JSON 및 DB 테이블(`service_pipeline_run`)에 기록.
- [x] **V. 단순성 및 점진적 진화 (Simplicity - YAGNI)**: 불필요한 과도한 추상화를 지양하고 직접적이고 안정적인 Graceful Fallback 구현.

---

## Project Structure

### Documentation (this feature)

```text
specs/012-restore-pilos-pipeline/
├── spec.md              # 기능 명세서
├── checklists/
│   └── requirements.md  # 품질 검증 체크리스트
├── plan.md              # 구현 계획서 (본 파일)
├── research.md          # 기술 조사 및 아키텍처 결정서
├── data-model.md        # 데이터 모델 및 엔터티 명세
├── quickstart.md        # 실행 및 검증 가이드
└── contracts/
    └── pipeline_contract.md # 인터페이스 계약서
```

### Source Code (repository root)

```text
ateam/pilos-sentiment-index/
├── pilos/
│   ├── jobs/
│   │   ├── collect_supply_demand.py  # [수정] 키움 API 부재 시 Graceful Fallback 처리
│   │   ├── run_service_pipeline.py   # [수정] 수급 스킵 상태 시 후속 단계 정상 진행
│   │   ├── predict_model.py          # [활용] 8/12~19 감성 지표 소급 추론
│   │   ├── generate_llm_reports.py   # [수정/활용] 8/12~19 보고서 소급 생성 및 단일 실패 격리
│   │   └── worker_daemon.py          # [운영] 10분 주기 자동 파이프라인 데몬
│   └── collection/
│       └── kiwoom_supply_demand.py   # [점검] 수급 클라이언트 예외 규격 정합
└── tests/
    ├── test_supply_demand_job.py     # [수정/추가] API 부재 Fallback 단위 테스트
    └── test_pipeline_status.py       # [수정/추가] 파이프라인 정상 완수 회귀 테스트

model_gateway/
└── config/
    └── server_config.json            # [수정] 기본 서빙 모델 qwen3.5-2b 및 vram_limit_mb 4000 설정

docker-compose.yml                    # [수정] SYNTHESIS_LLM_MODEL=qwen3.5-2b 등 환경변수 통일
```

**Structure Decision**: A-Team 파이프라인의 핵심 결함 지점(`collect_supply_demand.py`, `run_service_pipeline.py`) 및 공용 게이트웨이의 경량 모델 설정(`server_config.json`)을 직접 보완하여 전체 시스템 복원력을 완성합니다.

---

## Complexity Tracking

> *헌법 위반 사항 없음 (모든 게이트 100% 충족)*

---

## Phase Breakdown & Detailed Work Items

### Phase 0: Research & Discovery (Completed)
- 파이프라인 5단계 키움 API 예외로 인한 연쇄 중단 메커니즘 규명.
- LLM 게이트웨이의 3개 모델 서빙 및 GTX 1070 VRAM 점유 프로파일 분석.
- 8월 12일~19일 DB 데이터(댓글/일별문서 존재, 감성점수/보고서 부재) 실사 완료.

### Phase 1: Design & Contracts (Completed)
- `data-model.md`: 일별문서, 감성결과, LLM보고서, 수급, 파이프라인 감사로그 엔터티 정의.
- `pipeline_contract.md`: Graceful Fallback 인터페이스, 최상위 파이프라인 계약, LLM 보고서 소급 CLI 계약 정의.
- `quickstart.md`: 5단계 E2E 검증 절차 확립.

### Phase 2: Tasks Decomposition (`/speckit-tasks` 단계)
- Task 1: `collect_supply_demand.py` 및 `run_service_pipeline.py`에 Graceful Fallback 구현 및 단위 테스트 작성.
- Task 2: `model_gateway/config/server_config.json` 및 `docker-compose.yml` 기본 모델을 `qwen3.5-2b`로 전환하고 VRAM 점유량 < 4GB 검증.
- Task 3: 8월 12일~19일 구간 10개 전 종목 감성 모델 추론(`predict_model`) 및 LLM 보고서 생성(`generate_llm_reports`) 소급 실행.
- Task 4: `pilos-worker` 데몬 정상 가동 확인 및 웹 대시보드 200 OK 최종 E2E 검증.
