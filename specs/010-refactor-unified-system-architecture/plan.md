# Implementation Plan: 통합 시스템 아키텍처 점검 및 리팩토링 (010-refactor-unified-system-architecture)

**Branch**: `010-refactor-unified-system-architecture` | **Date**: 2026-08-18 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/010-refactor-unified-system-architecture/spec.md)

**Input**: Feature specification from `specs/010-refactor-unified-system-architecture/spec.md`

---

## Summary

본 계획은 단일 GPU(GTX 1070 8GB VRAM) 환경에서 발생하는 3대 챗봇(A-Team PILOS, B-Team 올리챗, B-Team 올원챗)의 모델 핫스왑 병목(20~30s) 및 PILOS 동기 워커 블로킹 현상을 해결하고, Nginx 게이트웨이 라우팅과 Oliview 프론트엔드 API 경로를 정규화하여 무지연·고가용성 통합 AI 플랫폼을 확립하는 종합 리팩토링 계획이다.

---

## Technical Context

**Language/Version**: Python 3.11/3.12, JavaScript/JSX (React 18 / Node.js 18+), Nginx 1.25+

**Primary Dependencies**: FastAPI, Flask, Gunicorn, Streamlit, vLLM / llama-cpp-python, PyTorch / CUDA (WSL2), React, Vite

**Storage**: MySQL 8.0 (`pilos_v2` for A-Team, `oliview_project` for B-Team), CSV/NPY Artifacts, In-memory Knowledge Cache

**Testing**: Python `unittest` (`tests/test_multi_chatbot_regression.py`), Contract Verification Tests

**Target Platform**: Linux Docker / Windows 11 WSL2 (NVIDIA GTX 1070 8GB VRAM)

**Project Type**: Multi-Service AI Platform / Reverse Proxy Gateway & Microservices

**Performance Goals**:
- PILOS 정본 지식 캐시 질의 < 50ms (SC-001)
- 동적 LLM 첫 번째 토큰 시간(TTFT) < 2.0s (SC-002)
- 동시 다중 질의 시 모델 핫스왑 0회 및 HTTP 200 100% 성공 (SC-003)
- 통합 회귀 테스트 스위트 10초 이내 100% 통과 (SC-004)
- Oliview 상품 상세 데이터 로딩 성공률 100% (SC-005)

**Constraints**:
- 단일 GPU 8GB VRAM 한계 내 상주 서빙 (`qwen3.5-4b`, `bge-m3`, `bge-reranker-v2-m3`)
- 포트 8080 단일 Ingress Nginx 역방향 프록시 진입점
- 기존 DB 스키마 및 가중치 파일의 비파괴적 무결성 보존

**Scale/Scope**: 3개 챗봇 서비스, 2개 메인 웹 포털, 1개 공용 AI 모델 서빙 게이트웨이, 1개 통합 Nginx 프록시

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. 언어 및 커뮤니케이션 정책 (Language Policy)**: `PASS`
  - 모든 사용자 대화, 명세서, 계획서, 계약서, 퀵스타트 문서가 한국어로 작성됨.
- **II. TDD 및 테스트 우선주의 (Test-First & Contract Verification)**: `PASS`
  - `test_multi_chatbot_regression.py` 통합 회귀 테스트 스위트 및 `/contracts/*` 인터페이스 계약 사전 구축.
- **III. 서비스 모듈화 및 격리 (Service Modularity & Environment Isolation)**: `PASS`
  - A-Team, B-Team, Model Gateway, Ingress Gateway가 Docker Compose 상에서 독립 컨테이너 및 브릿지 네트워크로 완벽 격리됨. 기존 가중치 및 DB 보존.
- **IV. 관측 가능성 및 구조화된 로깅 (Observability & Structured Logging)**: `PASS`
  - Nginx `json_analytics` 로깅 포맷, `X-Request-ID` 전파, Latency 추적 일관 적용.
- **V. 단순성 및 점진적 진화 (Simplicity & Incremental Evolution - YAGNI)**: `PASS`
  - 불필요한 프레임워크 추가 없이 단일 모델 통일(`qwen3.5-4b`) 및 표준 OpenAI 규격 준수로 단순화.

---

## Project Structure

### Documentation (this feature)

```text
specs/010-refactor-unified-system-architecture/
├── plan.md              # 본 계획서 (/speckit-plan)
├── research.md          # Phase 0 아키텍처 진단 및 기술 결정 (/speckit-plan)
├── data-model.md        # Phase 1 개체 모델 및 상태 전이 (/speckit-plan)
├── quickstart.md        # Phase 1 빠른 검증 가이드 (/speckit-plan)
├── contracts/           # Phase 1 인터페이스 계약서 (/speckit-plan)
│   ├── model-gateway-contract.md
│   ├── ingress-routing-contract.md
│   ├── chatbot-api-contracts.md
│   └── oliview-frontend-contract.md
└── tasks.md             # Phase 2 구현 작업 목록 (/speckit-tasks)
```

### Source Code (repository root)

```text
c:/AISERVICE/
├── docker-compose.yml              # 통합 멀티 서비스 컨테이너 오케스트레이션
├── gateway/
│   ├── Dockerfile
│   ├── nginx.conf                 # 통합 Nginx 역방향 프록시 설정 (8080)
│   └── html/                      # 통합 포털 랜딩 페이지
├── model_gateway/                 # 공용 AI 모델 서빙 게이트웨이 (vLLM/llama-cpp)
│   ├── Dockerfile
│   ├── config/
│   └── src/api/routes/
├── ateam/                         # A-Team PILOS 금융 분석 서브시스템
│   ├── docker-compose.yml
│   └── pilos-sentiment-index/     # PILOS Web (Flask/Gunicorn) & Worker
├── bteam/                         # B-Team 올리뷰 서브시스템
│   ├── Oliview_Project/           # 메인 웹 포털 (React Frontend & Flask Backend)
│   ├── Oliview_chatbot_a/         # 올리챗 (Streamlit)
│   └── Oliview_chatbot_b/         # 올원챗 (FastAPI)
└── tests/
    └── test_multi_chatbot_regression.py  # 3대 챗봇 통합 회귀 테스트 스위트
```

**Structure Decision**: A-Team, B-Team, Model Gateway, Ingress Gateway로 분리된 독립 서브시스템 구조를 유지하며, 단일 진입점 Nginx(8080)와 모델 게이트웨이(8081, 8090, 8091)를 통해 유기적으로 통합한다.

---

## Complexity Tracking

> **Constitution Check 위반 사항 없음 (Full Compliance)**

| 항목 | 내용 |
|---|---|
| **위반 사항 (Violations)** | 없음 (None) |
| **추가 복잡도 (Added Complexity)** | 없음 (표준 모델 및 경로 통일로 시스템 복잡도 대폭 감소) |

---

## Phase Execution Summary

- **Phase 0 (Outline & Research)**: `research.md` 작성 완료 (5대 핵심 기술 결정 및 근거 수립)
- **Phase 1 (Design & Contracts)**:
  - `data-model.md`: 핵심 데이터 개체 및 상태 전이도 정의
  - `contracts/`: Model Gateway, Ingress Routing, Chatbots, Oliview Frontend 4대 계약서 구축
  - `quickstart.md`: 통합 자동화 테스트 및 엔드포인트 검증 가이드 작성
- **Next Phase (Phase 2)**: `/speckit-tasks` 명령을 통한 실행 가능한 작업 목록(`tasks.md`) 생성
