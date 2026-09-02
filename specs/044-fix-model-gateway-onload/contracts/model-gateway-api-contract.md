# Interface Contract: 모델 게이트웨이 API 및 헬스체크 계약

**Feature**: `044-fix-model-gateway-onload`
**Date**: 2026-09-02
**Status**: Active

## 1. 헬스체크 및 서비스 준비도 엔드포인트

### 1.1 `GET /health/readiness`
- **목적**: Kubernetes / Docker / 프록시 서비스 준비도 판정 (기본 LLM 모델의 VRAM 온로드 및 포트 8089 헬스 통과 여부)
- **성공 응답 (HTTP 200)**:
  ```json
  {
    "status": "ready",
    "vram_offloaded_100pct": true,
    "model_id": "qwen3.5-2b"
  }
  ```
- **미준비 응답 (HTTP 503)**:
  ```json
  {
    "status": "not_ready",
    "vram_offloaded_100pct": false,
    "current_state": "LOADING"
  }
  ```

### 1.2 `GET /health` (종합 관측 엔드포인트)
- **목적**: 게이트웨이 및 LLM/임베딩/리랭커 서브프로세스의 통합 상태 모니터링
- **성공 응답 (HTTP 200)**:
  ```json
  {
    "status": "healthy",
    "model": "qwen3.5-2b",
    "active_models": ["qwen3.5-2b"],
    "backend_port": 8089,
    "is_ready": true,
    "vram_allocated_mb": 2600,
    "vram_total_mb": 8192,
    "auxiliary_models": {
      "embedding": {
        "model": "bge-m3",
        "port": 8090,
        "status": "READY"
      },
      "reranker": {
        "model": "bge-reranker-v2-m3",
        "port": 8091,
        "status": "READY"
      }
    }
  }
  ```

---

## 2. 추론 및 모델 서빙 엔드포인트

### 2.1 `POST /v1/chat/completions` (OpenAI 호환 채팅 추론)
- **목적**: LLM 챗봇 답변 생성 및 스트리밍
- **요청 헤더**: `Authorization: Bearer sk-...` (선택적 API Key), `Content-Type: application/json`
- **요청 바디**:
  ```json
  {
    "model": "qwen3.5-2b",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "안녕하세요!"}
    ],
    "stream": true,
    "max_tokens": 512,
    "temperature": 0.7
  }
  ```
- **성공 응답**: `HTTP 200` (SSE 스트림 `text/event-stream` 또는 `application/json`)

### 2.2 `POST /v1/embeddings` (임베딩 벡터 생성)
- **대상 포트**: 8090 (BGE-M3)
- **성공 응답**: `HTTP 200` (1024차원 float 배열)

### 2.3 `POST /v1/rerank` (문서 재순위화)
- **대상 포트**: 8091 (BGE-Reranker-v2-M3)
- **성공 응답**: `HTTP 200` (문서 인덱스 및 relevance_score 목록)
