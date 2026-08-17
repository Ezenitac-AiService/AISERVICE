# Implementation Plan: PILOS 챗봇 로컬 GPU 지연 해소 및 스트리밍·정본 캐시 가속 (008-pilos-chatbot-latency-optimization)

**Branch**: `008-pilos-chatbot-latency-optimization` | **Date**: 2026-08-18 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/008-pilos-chatbot-latency-optimization/spec.md)

**Input**: Feature specification from `/specs/008-pilos-chatbot-latency-optimization/spec.md`

---

## Summary

로컬 GPU(GTX 1070 8GB VRAM) 환경에서 발생하는 챗봇의 '답변 생각 중...' 무한 대기 및 타임아웃 오류(404/503)를 해결하고 타 챗봇(B-Team 올리챗, 올원챗)과의 완벽한 격리를 보장하기 위해:
1. **정본 지식 캐시(Knowledge Cache)**: 15개 정적 서비스 질문 블록에 대해 사전 검증된 정본 응답을 메모리 캐시에서 즉각(10~50ms) 반환하여 불필요한 GPU 부하를 100% 제거하고 타 챗봇용 공유 GPU 자원을 확보.
2. **실시간 SSE 스트리밍(Streaming)**: 동적 LLM 생성 요청에 대해 `text/event-stream` 기반 토큰 점진 출력을 적용하여 첫 토큰 방출 시간(< 5초) 단축 및 체감 대기 해소.
3. **타임아웃 및 재시도 현실화**: 백엔드 클라이언트 및 Nginx 게이트웨이 타임아웃을 120초로 확대하고 30초 조기 재시도 폭주를 제거하여 단일 완결성 확보.
4. **타 챗봇 무결성 격리 보장 (Non-Regression)**: 모든 코드 수정은 A-Team Pilos 내부로 국한하며, B-Team 올리챗(`bteam/chata/`), 올원챗(`bteam/chatb/`), 올리뷰 포털(`bteam/oliview/`) 경로 및 환경에 일체의 사이드 이펙트가 발생하지 않도록 철저히 격리.

---

## Technical Context

**Language/Version**: Python 3.11 (Flask 백엔드), Vanilla ES6+ JavaScript (프론트엔드)

**Primary Dependencies**: Flask, OpenAI SDK (`stream=True`), Nginx (Reverse Proxy)

**Storage**: In-memory Knowledge Cache (Python Dictionary), ChromaDB (서비스 정본 벡터 저장소 유지)

**Testing**: `pytest` (단위/계약/통합 테스트), `curl` 및 PowerShell E2E 검증, E2E 서브시스템(Chatbot A/B) 회귀 테스트

**Target Platform**: Docker 컨테이너 환경 (Linux / Windows Host)

**Project Type**: AI 챗봇 웹 서비스 및 리버스 프록시 게이트웨이

**Performance Goals**: 
- 정적 지식 질문 응답 시간: **< 100ms** (목표 < 50ms)
- 동적 LLM 첫 토큰 렌더링(TTFT): **< 5초**
- 타 챗봇(올리챗, 올원챗) 정상 가동률: **100% 유지**
- 타임아웃 120초 한도 내 단일 요청 성공률: **99.9%**

**Constraints**: 로컬 NVIDIA GeForce GTX 1070 8GB VRAM 하드웨어 제약 고려, 외부 추가 무거운 의존성 도입 금지 (YAGNI 준수), B-Team 서브시스템 코드 수정 금지

**Scale/Scope**: PILOS 챗봇 서비스 15개 고정 질문 블록 및 동적 종목 분석 챗봇 파이프라인

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| 원칙 (Constitution Principle) | 부합 여부 | 검증 내용 |
| :--- | :---: | :--- |
| **I. 언어 및 커뮤니케이션 정책** | **PASS** | 모든 산출물, 계획서, 코드 주석, 사용자 메시지 및 챗봇 응답은 표준 한국어로 작성됨 |
| **II. TDD 및 테스트 우선주의** | **PASS** | 캐시 조회, SSE 제너레이터, 타임아웃 정책 및 타 챗봇 회귀 테스트를 선행 구축 |
| **III. 서비스 모듈화 및 격리** | **PASS** | A-Team Pilos 내부 완결 구현으로 B-Team(올리챗, 올원챗) 코드 변경 0건, 환경 및 포트 충돌 방지 |
| **IV. 관측 가능성 및 로깅** | **PASS** | 스트리밍 시작/종료, 소요 시간, 캐시 히트 여부를 구조화된 로그로 기록 |
| **V. 단순성 및 점진적 진화 (YAGNI)** | **PASS** | Redis/외부 큐 도입 없이 인메모리 캐시와 표준 SSE 스트리밍으로 가장 단순하고 강력하게 구현 |

---

## Project Structure

### Documentation (this feature)

```text
specs/008-pilos-chatbot-latency-optimization/
├── spec.md              # 기능 명세서 (완료)
├── checklists/
│   └── requirements.md  # 명세 품질 체크리스트 (16/16 PASS)
├── plan.md              # 본 구현 계획서 (완료)
├── research.md          # 기술 조사 및 의사결정 기록 (Phase 0)
├── data-model.md        # 데이터 모델 및 상태 전이도 (Phase 1)
├── contracts/           # API 계약 명세서 (Phase 1)
│   └── chat_api_contract.md
└── quickstart.md        # 실행 및 검증 가이드 (Phase 1)
```

### Source Code (격리 범위: A-Team Pilos 내부로 한정)

```text
ateam/pilos-sentiment-index/
├── pilos/
│   ├── service/
│   │   ├── chatbot_service.py       # [MODIFY] 15개 정본 지식 캐시 우선 조회 및 분기 로직
│   │   ├── rag_service.py           # [MODIFY] 스트리밍 지원 LLM 호출 및 정본 캐시 소스 연동
│   │   └── knowledge_cache.py       # [NEW] 15개 정본 서비스 지식 인메모리 캐시 저장소
│   ├── collection/ai_clients/
│   │   └── llm_client.py            # [MODIFY] stream=True 지원, 120초 타임아웃, 재시도 폭주 제거
│   └── web/
│       ├── app.py                   # [MODIFY] SSE 스트리밍 Response 핸들러 및 라우트 정규화
│       └── static/js/
│           └── chat.js              # [MODIFY] ReadableStream 기반 실시간 타이핑 렌더러 & Abort 제어
tests/
├── test_chatbot_service.py          # [MODIFY] 캐시 히트 및 분기 단위 테스트 추가
├── test_llm_client_stream.py        # [NEW] LLM 스트리밍 제너레이터 및 타임아웃 계약 테스트
└── test_chat_api_stream.py          # [NEW] Flask SSE 스트리밍 엔드포인트 통합 테스트

# [보호 대상: 변경하지 않음]
bteam/
├── Oliview_Project/chatbot_A/       # [UNTOUCHED] 올리챗 Streamlit (8501)
└── Oliview_Project/chatbot_B/       # [UNTOUCHED] 올원챗 FastAPI (8002)

gateway/
└── nginx.conf                       # [VERIFY] 기존 B-Team 라우팅 보존 및 SSE 버퍼링 비활성화 확인
```

**Structure Decision**: B-Team 서브시스템 소스코드는 일체 수정하지 않으며, A-Team Pilos 내부에만 `knowledge_cache.py`를 신설하고 스트리밍 기능을 추가하여 서비스 간 완벽한 격리(Isolation)를 유지합니다.

---

## Complexity Tracking

> **Constitution Check 위반 사항 없음 (모든 원칙 100% 준수)**

| 항목 | 필요성 | 대안 대비 선택 이유 |
| :--- | :--- | :--- |
| **인메모리 딕셔너리 캐시** | 불변 정적 지식의 0ms 즉각 반환 | Redis 대비 추가 프로세스/컨테이너 의존성이 없어 가장 가볍고 빠름 |
| **SSE 스트리밍 (`text/event-stream`)** | 동적 생성 시 실시간 토큰 전달 | WebSocket 대비 단방향 전송에 최적화되고 Nginx 게이트웨이와 매끄럽게 호환됨 |
| **서브시스템 격리 보호** | B-Team 챗봇 무결성 보존 | Pilos 내부에만 변경을 한정하여 회귀 버그 원천 차단 |
