# Implementation Plan: 026-stabilize-2b-llm-chatbot

**Branch**: `026-stabilize-2b-llm-chatbot` | **Date**: 2026-08-20 | **Spec**: [`specs/026-stabilize-2b-llm-chatbot/spec.md`](file:///c:/AISERVICE/specs/026-stabilize-2b-llm-chatbot/spec.md)

## Summary

GTX 1070 (8GB VRAM) 환경에서 발생하는 모델 스와핑 핑퐁, CUDA OOM 크래시, 타임아웃 및 RAG 토큰 중간 절단 결함을 근본적으로 해결하기 위해, `model_gateway`에 `SINGLE_MODEL_MODE` 토글을 도입하여 3개 모델(`bge-m3`, `bge-reranker-v2-m3`, `qwen3.5-2b`)의 100% VRAM 상주 서빙 체제를 확립하고, 16K 컨텍스트 윈도우와 3단계 하이브리드 토큰 예산(512 / 2048 / 4096)을 전사 적용하여 4B에 버금가는 완성형 뷰티 솔루션을 100% 무중단으로 생성하도록 구현한다.

---

## Technical Context

- **Language/Version**: Python 3.12 (WSL2 Docker Linux & Windows 호스트 공통)
- **Primary Dependencies**: FastAPI, Uvicorn, Streamlit, `llama-cpp-python` (0.3.x / GGUF Server), `httpx`, `redis`, `pymysql`
- **Storage**: MySQL 8.0 (`bteam_db`, `pilos-db`), Redis 7 (`aiservice-redis` L2/L3 캐시)
- **Testing**: Python `unittest`, `pytest`, cURL & Docker Live Validation Scripts
- **Target Platform**: Windows 11 + WSL2 Docker (`vllm-serv-gateway`, `oliview_chatbot_a`, `oliview_chatbot_b`, `pilos-web`, `pilos-worker`)
- **Project Type**: Microservices AI Pipeline (Inference Gateway + Streamlit Chatbot + FastAPI RAG Backend + Stock Sentiment Pipeline)
- **Performance Goals**: TTFT < 1.5초, RAG 완성형 답변(2K) 생성 < 5.0초, OOM 크래시 0회, 타임아웃 0%
- **Constraints**: 호스트 GPU VRAM 8,192 MiB (GTX 1070 Pascal), 총 VRAM 점유 <= 6.0 GB 보장

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **언어 및 커뮤니케이션 정책 (Korean/English)**: 사용자 산출물 및 문서는 한국어, 내부 추론은 영어 준수.
- [x] **TDD 및 계약 검증 (Test-First)**: 게이트웨이 및 챗봇 인터페이스 계약(`contracts/`) 선행 정의.
- [x] **서비스 모듈화 및 격리 (Modularity)**: `model_gateway`, `bteam`, `ateam` 격리 보존 및 하위 호환성 유지.
- [x] **관측 가능성 및 구조화된 로깅 (Observability)**: 성능 지표(TTFT, TPS, Token Count) 및 보안 이벤트 로깅 유지.
- [x] **단순성 및 점진적 진화 (YAGNI & Non-Destructive)**: 기존 다중 모델 코드를 파괴하지 않고 `SINGLE_MODEL_MODE` 토글로 점진적 확장성 확보.

---

## Project Structure

### Documentation (this feature)

```text
specs/026-stabilize-2b-llm-chatbot/
├── spec.md              # 기능 명세서
├── plan.md              # 본 구현 계획서
├── research.md          # 기술 의사결정 및 근거
├── data-model.md        # 데이터 모델 및 스키마
├── quickstart.md        # 라이브 검증 시나리오
├── contracts/           # 인터페이스 계약 명세
│   ├── model_gateway_contract.md
│   └── chatbot_rag_contract.md
└── checklists/
    └── requirements.md  # 명세 품질 체크리스트
```

### Source Code Modifications

```text
model_gateway/
├── .env, .env.example
│   └── SINGLE_MODEL_MODE=true, DEFAULT_MODEL=qwen3.5-2b
├── config/model_config.json
│   └── current_model: "qwen3.5-2b", current_n_ctx: 16384
└── src/
    ├── api/routes/inference_api.py
    │   └── SINGLE_MODEL_MODE 가드 및 핫스왑 우회/고정 라우팅
    └── core/llama_manager.py
        └── 16K n_ctx 보장 및 자동 2B 상주 관리

bteam/
├── .env, .env.example
│   └── DEFAULT_MODEL=qwen3.5-2b, SYNTHESIS_LLM_MODEL=qwen3.5-2b, FAST_LLM_MODEL=qwen3.5-2b
├── Oliview_chatbot_a/
│   ├── .env, config.json
│   ├── llm_common.py
│   │   └── 2B 모델 단일화, max_tokens=2048 RAG 합성 예산 확장
│   └── oliview_core/guardrail.py
│       └── SYSTEM_PROMPT_LEAK_OUTPUT 오탐 제거 경계 조건 개선
├── Oliview_chatbot_b/
│   ├── project_ragapi.py
│   │   └── max_tokens=2048 하이브리드 토큰 정책 및 스트리밍 파싱 안정화
│   └── oliview_core/guardrail.py
│       └── 화장품 상품명/리뷰 오탐 방지 패턴 동기화
```

---

## Phase 0: Outline & Research

- [x] 8GB VRAM 토폴로지 분석 및 수학적 검증 완료 (`research.md`)
- [x] `SINGLE_MODEL_MODE` 토글 아키텍처 수립 완료 (`research.md`)
- [x] 3단계 하이브리드 토큰 정책 및 16K 컨텍스트 윈도우 확정 (`research.md`)
- [x] 보안 가드레일 오탐 원인 분석 및 완화 방안 수립 (`research.md`)

---

## Phase 1: Design & Contracts

- [x] 데이터 모델 및 설정 스키마 정의 완료 ([`data-model.md`](file:///c:/AISERVICE/specs/026-stabilize-2b-llm-chatbot/data-model.md))
- [x] 게이트웨이 및 챗봇 인터페이스 계약 정의 완료 ([`contracts/`](file:///c:/AISERVICE/specs/026-stabilize-2b-llm-chatbot/contracts))
- [x] 라이브 E2E 검증 시나리오 작성 완료 ([`quickstart.md`](file:///c:/AISERVICE/specs/026-stabilize-2b-llm-chatbot/quickstart.md))

---

## Complexity Tracking

> 본 설계는 헌법 위반 사항이 없으며, 기존 코드를 파괴하지 않고 환경변수 플래그 하나로 하위 호환성을 100% 보존합니다.
