# Configuration Contract: Tiered LLM Service Environment Variables

**Contract Version**: 1.0.0  
**Feature**: `013-tiered-llm-model-routing`

---

## 1. 전사 공통 환경변수 규격 (`.env`)

전사 루트 `.env` 파일에 정의되어 모든 컨테이너(`pilos_worker`, `pilos_web`, `oliview_backend`, `oliview_chatbot_a`, `oliview_chatbot_b`, `vllm-serv-gateway`)에 공통 주입되는 환경변수 규격입니다.

```env
# ============================================================================
# 전사 계층형 LLM 서빙 설정 (Tiered LLM Architecture)
# ============================================================================
# 기본 초고속 모델 (A팀 10분 정기배치, 단일댓글 감성, B팀 메타데이터 필터)
FAST_LLM_MODEL=qwen3.5-2b

# 고품질 심층 합성 모델 (B팀 RAG 다중리뷰 비교합성, A팀 복합투자 심층상담)
SYNTHESIS_LLM_MODEL=qwen3.5-4b

# 공통 모델 게이트웨이 엔드포인트
VLLM_GATEWAY_URL=http://vllm-serv-gateway:8081

# 임베딩 & 리랭킹 모델 규격
EMBEDDING_MODEL=bge-m3
RERANK_MODEL=bge-reranker-v2-m3
EMBEDDING_PORT=8090
RERANK_PORT=8091

# VRAM 안전 상한선 (GTX 1070 8GB 실측 기준)
VRAM_SAFETY_LIMIT_MB=5000
```

---

## 2. 각 팀 서비스별 환경변수 참조 매핑표

| 컨테이너 / 모듈 | 참조 환경변수 | 내부 기본값 | 용도 |
|---|---|---|---|
| `vllm-serv-gateway` | `FAST_LLM_MODEL`<br>`SYNTHESIS_LLM_MODEL`<br>`VRAM_SAFETY_LIMIT_MB` | `qwen3.5-2b`<br>`qwen3.5-4b`<br>`5000` | 상주 모델 초기화, 4B 온로드 및 우선순위 큐잉 |
| `pilos_worker` | `FAST_LLM_MODEL` | `qwen3.5-2b` | 10분 주기 10개 종목 일별 해설 보고서 생성 |
| `pilos_web` | `FAST_LLM_MODEL`<br>`SYNTHESIS_LLM_MODEL` | `qwen3.5-2b`<br>`qwen3.5-4b` | 단순 주가 질의(2B) / 심층 투자 상담(4B) 분기 |
| `oliview_chatbot_a` | `FAST_LLM_MODEL`<br>`SYNTHESIS_LLM_MODEL` | `qwen3.5-2b`<br>`qwen3.5-4b` | 질문 메타데이터 필터(2B) / 다중리뷰 RAG 합성(4B) |
| `oliview_chatbot_b` | `SYNTHESIS_LLM_MODEL` | `qwen3.5-4b` | RAG API 전문가 답변 합성 (1500토큰 가드) |
