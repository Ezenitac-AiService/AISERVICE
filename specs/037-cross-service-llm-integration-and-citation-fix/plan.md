# Implementation Plan: 037-cross-service-llm-integration-and-citation-fix

**Branch**: `037-cross-service-llm-integration-and-citation-fix` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/037-cross-service-llm-integration-and-citation-fix/spec.md`

---

## 1. Summary

본 계획은 Model Gateway Spec 036(2B 64K 상시 서빙 + 4B 32K 온디맨드 배치) 고도화와 **기술 실증/시연 플랫폼(GTX 1070 베이스라인)**의 특성을 반영하여, **(1) 상호보완형 다중 하이브리드 파이프라인 (Kiwi Fast-Path + Qwen 2B SLM Arbiter)**, **(2) LangGraph 코어 노드 도구화 (Typed Tools)**, **(3) 제로 서치 환각 방지 가드**, **(4) 본문 [리뷰 N] 및 UI 아코디언 1:1 무결성 & Python 후처리 가드레일**, **(5) 2단계 Top-P (문서 리랭킹 Top-P 85% + Qwen 토큰 생성 Top-P 0.85)**, **(6) 실증용 넉넉한 타임아웃(Inactivity 45s) & 눈속임 없는 실시간 진척도 피드백**, **(7) 사용자 주도 생성 중단(Stop) 및 서버 에러 투명 통지 체계**를 구현합니다.

---

## 2. Technical Context

- **Language/Version**: Python 3.10 / 3.11
- **Primary Dependencies**: FastAPI, Streamlit, LangGraph, ChromaDB, Kiwi-NLP (`kiwipiepy`), OpenAI Python SDK, BGE-M3 (임베딩/리랭킹), NumPy
- **Storage**: MySQL (화장품 메타데이터 및 배치 리포트), ChromaDB (리뷰 벡터 인덱스), Redis (임베딩/리랭킹 L2/L3 캐시)
- **Testing**: pytest (단위/통합 테스트), B-Team 7-Suite 통합 회귀 테스터 (`run_all_regression_tests.py`)
- **Target Platform**: Windows 11 / Linux Ubuntu Server (GTX 1070 8GB VRAM Baseline Platform)
- **Project Type**: Cross-Service AI System (Model Gateway + A-Team PILOS + B-Team Oliview ChatA/ChatB)
- **Operational Modes**:
  - `development` (POC / 시연 모드): Sliding Inactivity Timeout 45초, 총 타임아웃 180초 (GTX 1070 긴 프리필 수용)
  - `production` (운영 모드): Sliding Inactivity Timeout 15초, 총 타임아웃 60초
- **Performance Goals**:
  - Kiwi Fast-Path 정규화: $\le 3\text{ms}$
  - Qwen 2B SLM Fallback 분석 (필요 시): $\le 60\text{ms}$
  - LLM 첫 토큰 응답(TTFT): $\le 300\text{ms}$ (일반) / $\le 1500\text{ms}$ (GTX 1070 긴 프롬프트 프리필)
  - LLM 토큰 생성 속도: $\ge 50\text{ TPS}$ (2B 64K resident) / $\ge 30\text{ TPS}$ (4B 32K batch)
  - 사용자 '생성 중단' 클릭 시 반응 속도: $\le 500\text{ms}$
- **Constraints**:
  - 제로 서치(리뷰 0건) 시 허위 리뷰 창작율 $0.0\%$ (Strict Hallucination Guard)
  - 실제 파이프라인 전이 기반 실시간 상태 표시 (완전 눈속임 배제)
  - 서버/GPU 장애 발생 시 무한 로딩 없는 정직한 에러 통지

---

## 3. Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 체크 항목 | 준수 여부 | 설명 |
| :--- | :--- | :---: | :--- |
| **I. 언어 정책** | 한국어 산출물 작성 | **PASS** | 모든 명세서, 계획서, 테스트, 가이드라인을 한국어로 작성 |
| **II. TDD 원칙** | Test-First & Contract Verification | **PASS** | `test_entity_normalization.py`, `test_hybrid_parser.py`, `test_langgraph_tools.py`, `test_document_top_p.py`, `test_citation_integrity.py` 등 테스트 선행 구현 |
| **III. 서비스 격리** | 모듈 독립성 및 비파괴성 보존 | **PASS** | A-Team, B-Team, Model Gateway의 기존 포트/환경을 보존하며 비파괴적 어댑터 패턴 적용 |
| **IV. 관측 가능성** | 구조화된 로깅 및 추적 | **PASS** | `trace_id` 기반 로그, 파싱 소스(`KIWI` vs `SLM`), 도구 호출 메타데이터, SSE 하트비트, 투명한 에러 원인 통지 |
| **V. 단순성 (YAGNI)**| 점진적 진화 및 최소 복잡도 | **PASS** | Fast-Path DAG + 재사용 가능한 Typed LangGraph Tool 캡슐화로 복잡도 최소화 |

---

## 4. Project Structure

### Documentation (this feature)

```text
specs/037-cross-service-llm-integration-and-citation-fix/
├── spec.md              # 요구사항 명세서
├── plan.md              # 구현 계획서 (본 파일)
├── research.md          # 기술 결정 및 리서치 분석 (Phase 0)
├── data-model.md        # 데이터 모델 및 클래스 정의 (Phase 1)
├── quickstart.md        # 검증 및 실행 가이드 (Phase 1)
├── contracts/           # API 및 인용 스키마 정의 (Phase 1)
│   ├── gateway_client_contract.json
│   └── citation_contract.json
└── checklists/
    └── requirements.md  # 명세 품질 체크리스트
```

### Source Code Layout

```text
# 1. B-Team Chatbot A & B Core
bteam/
├── Oliview_chatbot_a/
│   ├── app.py / 06.02.app.py               # Streamlit UI (인용 아코디언, Stop 버튼, 에러 바운더리)
│   ├── graph_adapter.py                    # 실제 파이프라인 이벤트 스트림 및 인용 어댑터
│   └── oliview_core/
│       ├── config.py                       # Dev/Prod 환경별 타임아웃 (Inactivity 45s)
│       ├── client.py                       # LLM SSE 클라이언트 (Top-P 0.85 주입, Stop 취소 시 소켓 클로즈)
│       ├── tools/                          # [신규] LangGraph 표준 도구 모듈
│       │   ├── search_tools.py             # tool_search_catalog, tool_get_reviews
│       │   └── spec_tools.py               # tool_get_specs
│       └── nodes/
│           ├── router_node.py              # 하이브리드 파서(Kiwi + Qwen 2B SLM) & FEATURE_DISCOVERY 라우팅
│           ├── search_node.py              # 도구 기반 검색 실행
│           ├── rerank_node.py              # 문서 동적 Top-P (85%) & 점수 절벽 컷오프
│           ├── context_node.py             # <context> 조립 및 순위 부여
│           └── synthesis_node.py           # 제로 서치 가드 & 인라인 인용 프롬프트 & 후처리 가드레일
├── Oliview_chatbot_b/                      # ChatB Web API & 동일 코어 모듈 동기화
│   └── ...
└── Oliview_LLM/
    ├── common.py                           # 3-Tier 컨텍스트 파라미터 공통 정의
    └── run_all_regression_tests.py         # B-Team 7-Suite 통합 회귀 러너

# 2. A-Team PILOS Sentiment System
ateam/
└── pilos-sentiment-index/
    └── pilos/
        ├── collection/ai_clients/
        │   └── llm_client.py               # 게이트웨이 표준 클라이언트 (Top-P 0.85)
        └── service/
            ├── rag_service.py              # PILOS RAG 시스템 (2B 64K)
            └── report_service.py           # 일일 50건 뉴스 분석 리포트 (4B 32K)
```

---

## 5. Implementation Phases & Milestones

### Phase 1: Test-First Harness & Core Data Model (TDD)
- **T1.1**: 하이브리드 질의 파서 단위 테스트 (`test_hybrid_parser.py`) - 신조어/속성명 충돌/오탈자 검증 (Red).
- **T1.2**: LangGraph 도구 모듈 단위 테스트 (`test_langgraph_tools.py`) - `tool_search_catalog`, `tool_get_reviews`, `tool_get_specs` 검증 (Red).
- **T1.3**: 문서 동적 Top-P 단위 테스트 (`test_document_top_p.py`) (Red).
- **T1.4**: 제로 서치 환각 방지 및 인용 무결성 테스트 (`test_citation_integrity.py`) (Red).
- **T1.5**: POC 타임아웃 및 생성 중단/에러 핸들링 테스트 (`test_pipeline_feedback.py`) (Red).

### Phase 2: B-Team Core Hybrid Parser, Tools & 2-Stage Top-P Implementation
- **T2.1**: `entity_normalizer.py`에 Stage 1 Kiwi Fast-Path + Stage 2 Qwen 2B SLM 구조화 Fallback 하이브리드 파서 구현.
- **T2.2**: `oliview_core/tools/`에 LangGraph Typed Tool (`search_tools.py`, `spec_tools.py`) 구현.
- **T2.3**: `router_node.py` 및 `search_node.py`에 하이브리드 파서 및 `FEATURE_DISCOVERY` 도구 연동.
- **T2.4**: `rerank_node.py`에 문서 동적 Top-P ($P_{\text{doc}} \ge 0.85$) 및 Score Cliff ($\Delta > 0.25$) 조기 컷오프 로직 구현.
- **T2.5**: `synthesis_node.py` 프롬프트 템플릿 개편 (`ZERO_SEARCH_TEMPLATE`, 네임스페이스 인라인 인용 `[리뷰 N]`, `[제품명 리뷰 N]`, `[Turn N 리뷰 M]` 강제 및 Python 후처리 정규화 가드레일).
- **T2.6**: `client.py`에 최신 Top-P Nucleus Sampling (`top_p: 0.85`, `temperature: 0.3`, `repetition_penalty: 1.05`) 및 Dev 모드 넉넉한 타임아웃(Inactivity 45s) 주입.

### Phase 3: UI Real-time Feedback, Stop Control & Citation Synchronization
- **T3.1**: `graph_adapter.py` 및 `app.py` / `06.02.app.py`에서 실제 파이프라인 단계 시각화, 사용자 '생성 중단' 버튼, 장애 시 명확한 에러 메시지(`st.error`) 렌더링.
- **T3.2**: `📚 참조 리뷰 원문` 아코디언 및 카드 렌더링을 본문 인용 태그와 1:1로 정확히 동기화.
- **T3.3**: ChatB (`Oliview_chatbot_b`) Web UI 및 SSE 이벤트 스트림에도 동일한 피드백/중단/인용 로직 동기화.

### Phase 4: A-Team (PILOS) Model Gateway Integration Standard
- **T4.1**: `ateam/pilos-sentiment-index/pilos/collection/ai_clients/llm_client.py` 표준화 (Top-P 0.85, 2B 64K / 4B 32K 라우팅).
- **T4.2**: 일일 50건 뉴스 감성 분석 배치 리포트 서비스에서 `qwen3.5-4b` 32K 모델 호출 무결성 검증.

### Phase 5: Verification & Full Regression
- **T5.1**: Phase 1의 모든 단위/통합 테스트 Green 확인.
- **T5.2**: B-Team 7-Suite 통합 회귀 테스트 (`run_all_regression_tests.py`) 100% 통과 검증.
- **T5.3**: 사용자 제시 실패 케이스("컬러그램 탕후루 꿀로스", "민감성 피부 쿠션팩트", "가상 상품", "중단 클릭", "장애 안내") 실시간 검증.
