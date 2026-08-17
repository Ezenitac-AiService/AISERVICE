# Implementation Plan: RAG 브랜드 엔티티 인식 및 데이터 결측치 배제·올리뷰 브랜드 조회 정규화 (006-rag-brand-guardrail)

**Branch**: `006-rag-brand-guardrail` | **Date**: 2026-08-17 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/006-rag-brand-guardrail/spec.md)

**Input**: Feature specification from `specs/006-rag-brand-guardrail/spec.md`

---

## Summary

올리뷰 서비스 전반의 브랜드 검색 정확도를 높이고 챗봇 RAG의 브랜드 환각 및 결측치 오류를 해결하기 위해 다음 4가지 개선을 일괄 적용합니다:
1. **올리뷰 React 프론트엔드 URL 접두사 정규화**: `App.jsx`의 `API_BASE_URL`을 `'/bteam/oliview'`로 변경하여 로그인/회원가입 브랜드 조회 시 Double `/api/` 404 오류를 영구 해결합니다.
2. **SQL 레벨 데이터 품질 가드레일**: RAG DB 조회 시 `brand_name` 및 `product_name`이 `NULL`, `''`, `미분류`인 결측치 데이터(전체 56.6%)를 100% 원천 배제합니다.
3. **불용어(Stopwords) 필터링 및 브랜드 엔티티 감지**: 사용자 질문에서 '제품', '추천' 등 일반 불용어를 제거하고, 3,062개 등록 브랜드명을 사전 매칭하여 부재 브랜드 질의 시 0-결과 표준 안내문을 즉시 반환합니다.
4. **프롬프트 네거티브 가드레일 강화**: LLM 컨텍스트에 `[익명]`이나 타사 브랜드를 질문의 브랜드로 지어내지 못하도록 엄격한 네거티브 제약을 주입합니다.

---

## Technical Context

- **Language/Version**: Python 3.12, JavaScript (React 18 / Vite), SQL
- **Primary Dependencies**: FastAPI, Flask, Gunicorn, httpx, pymysql, regex
- **Storage**: MySQL (`oliview_project` DB)
- **Testing**: React 프론트엔드 브랜드 모달 조회 테스트, RAG 자연어 질의 검증, `verify_e2e_services.ps1` 전체 체크포인트 검증
- **Target Platform**: Docker 컨테이너 (`oliview_frontend`, `oliview_backend:5050`, `oliview_chatbot_b:8002`, `gateway:8080/8443`)
- **Performance Goals**: 브랜드 엔티티 파싱 지연 1ms 이하, 부재 브랜드 환각율 0.0%
- **Constraints**: 기존 정상 브랜드(예: '차앤박', '라네즈' 등) RAG 검색 및 10대 체크포인트 무결성 100% 보존

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Language Requirement)**: 모든 명세, 설계, 프롬프트, 브랜드 부재 안내문 한국어 완벽 대응 (PASS).
- **Principle II (Test-Driven Discipline)**: '헤라', '샤넬', '차앤박' 등 실제 질의 검증 시나리오 및 E2E 스위트 정합성 완비 (PASS).
- **Principle III (Service Modularity & Isolation)**: `bteam/Oliview_Project/frontend` 및 `bteam/Oliview_chatbot_b/` 내부 변경에 국한 (PASS).
- **Principle IV (Observability & Production Safeguards)**: 브랜드 엔티티 감지 로깅 및 0-결과 안전 폴백 완비 (PASS).
- **Principle V (YAGNI & Scope Economy)**: 요청된 브랜드 조회 404 해결 및 RAG 브랜드 가드레일에 집중 (PASS).

---

## Project Structure

### Documentation (this feature)

```text
specs/006-rag-brand-guardrail/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 research & technical decisions
├── data-model.md        # Phase 1 schemas & stopwords set
├── quickstart.md        # Phase 1 validation guide
├── contracts/
│   ├── brand-search-api.md   # Phase 1 Brand search API contract
│   └── rag-brand-guardrail.md# Phase 1 RAG brand guardrail contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 task decomposition (/speckit-tasks)
```

### Source Code Touched

```text
bteam/
├── Oliview_Project/frontend/src/App.jsx  # Fix API_BASE_URL (Double /api/ fix)
├── Oliview_chatbot_b/
│   ├── common.py                         # Brand entity matcher & stopwords filter
│   └── project_ragapi.py                 # SQL guardrail, entity detection, prompt update
└── Oliview_chatbot_a/
    └── llm_common.py                     # Synchronize brand guardrails for ChatA
```

---

## Implementation Steps & Phases

### Phase 1: 올리뷰 프론트엔드 URL 접두사 정규화
- `bteam/Oliview_Project/frontend/src/App.jsx`의 `API_BASE_URL`을 `'/bteam/oliview'`로 변경.

### Phase 2: 불용어 세트 및 브랜드 엔티티 매처 구현
- `bteam/Oliview_chatbot_b/common.py`에 `RAG_STOPWORDS`, `load_brand_names_cache`, `extract_brand_entity` 함수 구현.

### Phase 3: RAG 파이프라인 SQL 결측치 배제 및 부재 브랜드 방어
- `bteam/Oliview_chatbot_b/project_ragapi.py` 수정:
  - 1단계 DB 쿼리에 결측치 배제 조건(`brand_name != ''`, `product_name != ''`) 추가.
  - 불용어 제외 토큰 추출 및 브랜드 엔티티 사전 매칭 적용.
  - 부재 브랜드 질의 시 0-결과 표준 안내문 반환.
  - 시스템 프롬프트에 브랜드 환각 방지 네거티브 가드레일 추가.

### Phase 4: 컨테이너 갱신 및 종합 검증
- `oliview_frontend`, `oliview_chatbot_b`, `oliview_chatbot_a` 컨테이너 재기동.
- "헤라", "차앤박" 브랜드 검색 및 질의 검증.
- `verify_e2e_services.ps1` 10/10 PASS 확인.
