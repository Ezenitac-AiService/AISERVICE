# Quickstart Validation Guide: 013-tiered-llm-model-routing

**Feature**: `013-tiered-llm-model-routing`  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

---

## 1. 개요 (Overview)

본 가이드는 전사 2단계 계층형 LLM 라우팅(`qwen3.5-2b` 고속 기본 vs `qwen3.5-4b` 고품질 심층), CPU 임베딩/리랭커 오프로딩, 우선순위 큐 및 VRAM 안정성을 실전 검증하기 위한 엔드투엔드(E2E) 테스트 절차서입니다.

---

## 2. 사전 준비 (Prerequisites)

1. 도커 컨테이너 가동 확인:
   ```bash
   docker ps --filter "name=aiservice" --filter "name=pilos" --filter "name=oliview" --filter "name=vllm"
   ```
2. GPU VRAM 상태 확인 (기준: GTX 1070 8GB, 가용 >= 5.0GB):
   ```bash
   nvidia-smi
   ```

---

## 3. 단계별 검증 시나리오 (Verification Scenarios)

### 시나리오 1: 게이트웨이 상태 및 CPU 임베딩/리랭커 VRAM 0MB 검증
```bash
curl -s http://127.0.0.1:8081/health/vram | jq .
```
- **기대 결과**:
  - `gpu.used_vram_mb <= 5000`
  - `auxiliary_services.embedding_bge_m3.vram_mb == 0`
  - `auxiliary_services.reranker_bge_m3.vram_mb == 0`

---

### 시나리오 2: 2B 초고속 기본 모델 호출 및 JSON 스키마 검증 (A팀 리포트 시뮬레이션)
```bash
curl -X POST http://127.0.0.1:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5-2b",
    "priority": "low",
    "messages": [
      {"role": "system", "content": "JSON 형식으로만 주식 시장 지표 요약을 작성하세요."},
      {"role": "user", "content": "삼성전자 점수 86점 상승 요인"}
    ],
    "response_format": {"type": "json_object"}
  }' | jq .
```
- **기대 결과**: 2초 이내 응답 반환, 유효한 JSON 형식, `model: "qwen3.5-2b"`

---

### 시나리오 3: 4B 고품질 RAG 심층 합성 및 1,500 토큰 가드레일 검증 (B팀 챗봇 시뮬레이션)
```bash
curl -X POST http://127.0.0.1:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5-4b",
    "priority": "high",
    "messages": [
      {"role": "system", "content": "당신은 화장품 전문 어시스턴트입니다."},
      {"role": "user", "content": "민감성 피부용 진정 크림 3종의 장단점을 종합 비교해줘."}
    ]
  }' | jq .
```
- **기대 결과**: 5초 이내 고품질 한국어 비교 답변 반환, `model: "qwen3.5-4b"`

---

### 시나리오 4: 2B 배치 중 4B 인터랙티브 챗봇 우선순위 선점 (Preemption) 검증
- A팀 백그라운드 10개 종목 배치를 실행하는 동시에 B팀 챗봇 질의를 전송하여, 챗봇이 2초 이내에 락을 우선 획득하여 응답하는지 검증합니다.

---

### 시나리오 5: 자동 계약 검증 테스트 실행
```bash
docker exec vllm-serv-gateway pytest tests/test_tiered_routing_contract.py -v
```
- **기대 결과**: 모든 계약 테스트 통과 (100% Passed)
