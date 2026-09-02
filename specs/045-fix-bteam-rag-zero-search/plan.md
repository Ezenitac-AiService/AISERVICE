# Implementation Plan: Oliview B-Team RAG 파이프라인 DB/리랭커 복구 및 64K q8_0 KV 양자화 OOM 방지 (Feature 045)

**Feature Branch**: `045-fix-bteam-rag-zero-search`
**Date**: 2026-09-02
**Status**: Ready for Tasks (`/speckit-tasks`)

## Technical Context

- **언어 및 프레임워크**: Python 3.12, FastAPI, Streamlit, PyMySQL, ChromaDB, llama-cpp-python
- **주요 터치포인트 파일**:
  - `bteam/oliview_core/db.py`: `fetch_review_metadata` SQL 쿼리 교체 (`vw_chroma_review_sentences` 조인)
  - `bteam/Oliview_chatbot_a/oliview_core/db.py`: 챗봇 A 로컬 db 모듈 동기화
  - `bteam/Oliview_chatbot_b/oliview_core/db.py`: 챗봇 B 로컬 db 모듈 동기화
  - `bteam/oliview_core/rerank.py`: `BGEReranker.rerank()`에 `scores is None` 안전 Fallback 방어 코드 추가
  - `bteam/Oliview_chatbot_a/oliview_core/rerank.py`: 챗봇 A 로컬 rerank 모듈 동기화
  - `bteam/Oliview_chatbot_b/oliview_core/rerank.py`: 챗봇 B 로컬 rerank 모듈 동기화
  - `model_gateway/src/core/process_manager.py`: `build_server_command`에서 `n_ctx >= 32768`일 때 `--type_k q8_0 --type_v q8_0` 주입
  - `model_gateway/src/core/auxiliary_manager.py`: `check_and_recover_crashes`에서 UNLOADED/ERROR 상태 자동 스폰 복구 보강

## Constitution Check (v1.2.0)

| 원칙 | 준수 여부 | 확인 내용 |
|:---|:---:|:---|
| **원칙 I: 아키텍처 토폴로지** | PASS | 8081(FastAPI), 8089(LLM), 8090(Embedding), 8091(Reranker) 구조 엄격 준수 |
| **원칙 II: 데이터 격리** | PASS | B-Team MySQL `oliview_project` 스키마 및 ChromaDB 독립 유지 |
| **원칙 III: AI 모델 서빙** | PASS | GPU VRAM 완전 온로드 및 64K KV 캐시 양자화 적용 |
| **원칙 IV: 관측 가능성** | PASS | 구조화 JSON 로깅 및 Trace ID 전파 유지 |
| **원칙 V: 방어적 개발** | PASS | 리랭커 실패 시 `TypeError` 방지 및 무중단 1차 검색 Fallback |
| **원칙 VI: 모드 규율** | PASS | DEMO/PRODUCTION 모드별 타임아웃 유지 |
| **원칙 VII: 포괄적 무하드코딩** | PASS | DB 및 모델 엔드포인트 SSOT 환경변수 바인딩 |

## Implementation Phases

### Phase 0: Research & Exploration
- [x] 64K KV 캐시 양자화(q8_0) 메모리 절감 및 OOM-Kill 방지 효과 검증
- [x] MySQL `vw_chroma_review_sentences` 뷰 및 조인 스키마 검증
- [x] 리랭커 `None` 반환 시 Fallback 방어 메커니즘 설계

### Phase 1: Core Design & Contracts
- [x] `specs/045-fix-bteam-rag-zero-search/data-model.md` 생성
- [x] `specs/045-fix-bteam-rag-zero-search/contracts/rag-pipeline-contracts.md` 생성
- [x] `specs/045-fix-bteam-rag-zero-search/quickstart.md` 생성

### Phase 2: Implementation Touchpoints
1. **모델 게이트웨이 64K q8_0 KV 양자화 주입 ([process_manager.py](file:///c:/AISERVICE/model_gateway/src/core/process_manager.py))**
   - `build_server_command`에 `--type_k q8_0 --type_v q8_0` 조건 주입.
2. **모델 게이트웨이 보조 모델 자가치유 루프 개선 ([auxiliary_manager.py](file:///c:/AISERVICE/model_gateway/src/core/auxiliary_manager.py))**
   - `check_and_recover_crashes`에서 UNLOADED/ERROR 상태 및 프로세스 부재 시 자동 복원.
3. **B-Team DB 메타데이터 SQL 스키마 수정 ([db.py](file:///c:/AISERVICE/bteam/oliview_core/db.py))**
   - `vw_chroma_review_sentences` 기반 정상 메타데이터 조회 쿼리로 교체.
4. **B-Team 리랭커 NoneType Fallback 방어 코드 추가 ([rerank.py](file:///c:/AISERVICE/bteam/oliview_core/rerank.py))**
   - `scores is None` 시 즉시 안전 기본 점수 목록 생성.
5. **모듈 전수 동기화**
   - `bteam/Oliview_chatbot_a` 및 `bteam/Oliview_chatbot_b` 하위 모듈 동기화.
6. **회귀 테스트 및 실측 검증**
   - 단위 테스트 작성 및 챗봇 A/B 실질 RAG 질의 E2E 테스트 실행.
