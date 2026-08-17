# Quickstart & Verification Guide: 통합 AI 서비스 게이트웨이 및 서비스 격리

**Feature**: `001-unified-services-gateway`

**Date**: 2026-08-17

**Target Branch**: `001-unified-services-gateway`

---

## 1. Prerequisites (사전 준비)

- Docker Engine & Docker Compose v2.20+ 설치
- NVIDIA GPU Driver & NVIDIA Container Toolkit (Model Gateway 가속용)
- Git 저장소 최신 상태 확인 (`c:\AISERVICE`)

---

## 2. Environment Setup (환경 설정)

프로젝트 루트의 통합 `.env` 파일을 구성합니다:

```bash
# 루트 디렉터리 c:\AISERVICE 에서 실행
cp .env.example .env
```

`.env` 핵심 설정값 확인:
```env
# Gateway Port (기본 80, 충돌 시 8080 등으로 변경)
GATEWAY_PORT=80

# Model Gateway 내부 설정
SERVER_HOST=http://vllm-serv-gateway
MAIN_PORT=8081
FAST_LLM_MODEL=qwen3.5-2b
SYNTHESIS_LLM_MODEL=qwen3.5-4b
EMBEDDING_MODEL=bge-m3
RERANK_MODEL=bge-reranker-v2-m3
```

---

## 3. Launching Unified Services (통합 서비스 기동)

단일 통합 명령어로 전체 9개 서비스를 기동합니다:

```bash
# 전체 스택 빌드 및 백그라운드 기동
docker compose up -d --build
```

컨테이너 상태 및 헬스체크 확인:
```bash
docker compose ps
```

*모든 컨테이너가 `Up` 또는 `healthy` 상태인지 확인합니다.*

---

## 4. End-to-End Verification Scenarios (엔드투엔드 검증 시나리오)

### Scenario 1: 통합 포털 랜딩 페이지 접근 (`/`)
1. 브라우저에서 `http://localhost/` (또는 `http://localhost:8080/`) 접속.
2. **기대 결과**: AISERVICE 통합 포털 랜딩 페이지가 표시되고 4개 서비스(B-Team Oliview, 올리챗, 올원챗, A-Team Pilos) 바로가기 카드가 렌더링됨.

### Scenario 2: B-Team Oliview 메인 및 사이드바 챗봇 내비게이션 (`/bteam/oliview`)
1. 포털에서 'B-Team Oliview' 카드 클릭 또는 `http://localhost/bteam/oliview` 직접 접속.
2. 메인 대시보드 화면이 정적 에셋(CSS/JS) 깨짐 없이 로드되고 백엔드 API와 정상 통신하는지 확인.
3. 좌측 사이드바의 '🤖 올리챗' 버튼 클릭 ➔ 새 탭에서 `http://localhost/bteam/chata`로 이동.
4. 좌측 사이드바의 '🤖 올원챗' 버튼 클릭 ➔ 새 탭에서 `http://localhost/bteam/chatb`로 이동.

### Scenario 3: 올리챗(Streamlit) Multi-tier LLM 질의 검증 (`/bteam/chata`)
1. `http://localhost/bteam/chata`에서 상품 리뷰 관련 질의 입력.
2. **기대 결과**: WebSocket 끊김 없이 `bge-m3` 임베딩 및 `qwen3.5-2b`/`qwen3.5-4b` 모델과 통신하여 토큰 잘림 없이 실시간 답변 스트리밍 완료.

### Scenario 4: 올원챗(FastAPI) 복합 RAG 질의 검증 (`/bteam/chatb`)
1. `http://localhost/bteam/chatb`에서 상세 분석 질문 입력.
2. **기대 결과**: 하이브리드 RAG 검색 및 `qwen3.5-4b` 합성 모델을 통해 고품질 상세 답변 생성 완료.

### Scenario 5: A-Team Pilos 웹 대시보드 및 챗봇 검증 (`/ateam/pilos`)
1. `http://localhost/ateam/pilos` 접속.
2. 종목 감정 분석 대시보드 및 내장 챗봇/리포트 요약 기능이 정상 작동하는지 확인.

### Scenario 6: 포트 보안 격리 검증 (Security Isolation Check)
1. 외부 호스트 터미널에서 내부 포트 직접 접속 시도:
   ```bash
   curl -I http://localhost:8081/health    # Model Gateway 직접 접속
   curl -I http://localhost:3306          # MySQL 직접 접속
   ```
2. **기대 결과**: `Connection Refused` 또는 접속 불가로 외부 노출 차단 확인.

---

## 5. Teardown (서비스 종료)

```bash
docker compose down
```
