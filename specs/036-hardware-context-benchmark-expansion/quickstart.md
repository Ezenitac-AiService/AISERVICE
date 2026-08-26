# Quickstart Validation Guide: 036-hardware-context-benchmark-expansion

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)  
**Date**: 2026-08-26  
**Status**: Ready

---

## 1. Prerequisites

- Docker Desktop 및 WSL2 활성화.
- `vllm-serv` 및 `oliview_chatbot_b` 컨테이너 기동 상태.
- NVIDIA GeForce GTX 1070 8GB (또는 상위 GPU).

---

## 2. Validation Scenarios

### 시나리오 1: 하드웨어 감응형 프로파일 및 2B (64K Standard) 상시 서빙 검증

1. **게이트웨이 하드웨어 프로파일 엔드포인트 호출**:
   ```bash
   curl -s http://127.0.0.1:8081/v1/profile | jq .
   ```
   * **예상 결과**:
     * `tier`: `"BASELINE_8GB"`
     * `resident_model`: `"qwen3.5-2b"`
     * `resident_standard_n_ctx`: `65536`
     * `resident_ultra_n_ctx`: `131072`

2. **2B 64K 실제 한국어 추론 및 TPS SLA 검증**:
   ```bash
   docker compose exec -T oliview_chatbot_b python -c "
   import requests, time
   payload = {
       'model': 'qwen3.5-2b',
       'messages': [{'role': 'user', 'content': '올리브영 인기 남성 화장품 5가지를 추천해줘.'}],
       'max_tokens': 50
   }
   t0 = time.perf_counter()
   res = requests.post('http://vllm-serv:8081/v1/chat/completions', json=payload).json()
   el = time.perf_counter() - t0
   print(f'Elapsed: {el:.2f}s | Response: {res[\"choices\"][0][\"message\"][\"content\"][:40]}...')
   "
   ```
   * **예상 결과**: `Elapsed` $\le 1.5\text{s}$, TPS $\ge 50\text{ tokens/s}$.

---

### 시나리오 2: 4B (32K) 고품질 배치 스왑 및 복귀 검증

1. **4B (32K) 온디맨드 스왑 요청**:
   ```bash
   docker compose exec -T oliview_chatbot_b python -c "
   import requests, time
   payload = {
       'model': 'qwen3.5-4b',
       'messages': [{'role': 'user', 'content': '올리브영 2026 트렌드 요약 리포트를 100자로 작성해줘.'}],
       'max_tokens': 50
   }
   t0 = time.perf_counter()
   res = requests.post('http://vllm-serv:8081/v1/chat/completions', json=payload).json()
   el = time.perf_counter() - t0
   print(f'4B Inference Elapsed: {el:.2f}s')
   "
   ```
   * **예상 결과**: 초기 스왑 로드 시간 포함 약 38초 후 정상 완결, 이후 연속 호출 시 TPS $\ge 32\text{ tokens/s}$.

---

### 시나리오 3: B-Team 챗봇 7대 회귀 테스트 무결점 검증

1. **회귀 테스트 러너 실행**:
   ```bash
   docker compose exec -T oliview_chatbot_b python tests/run_all_regression_tests.py
   ```
   * **예상 결과**:
     * 7개 스위트 (ChatA, ChatB, Router, RAG, Evaluator, Session, Fallback) **100% ALL PASSED** (0 failures).
