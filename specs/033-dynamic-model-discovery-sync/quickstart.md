# Quickstart & Verification Guide: Dynamic Model Discovery

**Feature**: `033-dynamic-model-discovery-sync`  
**Date**: 2026-08-26  
**Status**: Runnable Verification Guide

---

## 1. 전제 조건 (Prerequisites)

* Docker 컨테이너 정상 가동: `vllm-serv-gateway`, `oliview_chatbot_b`, `aiservice-redis`
* GPU: NVIDIA GTX 1070 (8GB VRAM) 또는 상위 GPU
* 서빙 모델: `qwen3.5-2b` (포트 8089/8081, `n_ctx=16384`), `bge-m3` (포트 8090), `bge-reranker-v2-m3` (포트 8091)

---

## 2. 검증 시나리오 (Verification Scenarios)

### 시나리오 1: 게이트웨이 활성 모델 프로파일 조회 (`GET /v1/models`)
게이트웨이가 현재 16K 컨텍스트 및 `qwen3.5-2b` 활성 상태를 정확히 제공하는지 확인합니다.

```bash
docker exec vllm-serv-gateway python -c "
import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8081/v1/models')
with urllib.request.urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    print('✅ Available Models:', data)
"
```

---

### 시나리오 2: 클라이언트 동적 모델 탐색 (`discover_active_model()`)
챗봇 B 컨테이너 내부에서 `AiGatewayClient`가 게이트웨이의 활성 모델을 동적으로 탐색하고 캐싱하는지 확인합니다.

```bash
docker exec oliview_chatbot_b python -c "
from oliview_core.client import AiGatewayClient
client = AiGatewayClient()
discovered = client.discover_active_model()
print(f'✅ Discovered Active Model: {discovered}')
assert '2b' in discovered.lower()
"
```

---

### 시나리오 3: 4B 레거시 요청 시 2B(16K) 투명 매핑 스트리밍 생성
클라이언트가 `model: "qwen3.5-4b"`를 명시하여 요청하더라도 게이트웨이가 프로세스 킬 없이 상주 2B(16K)로 즉시 서빙하는지 검증합니다.

```bash
docker exec oliview_chatbot_b python -c "
import time
from oliview_core.client import AiGatewayClient
client = AiGatewayClient()
t0 = time.time()
tokens = []
for tok in client.generate_stream(prompt='올리브영 인기 세럼 추천해줘', system_prompt='너는 올리뷰 AI야', max_tokens=40):
    tokens.append(tok)
elapsed = time.time() - t0
print(f'✅ Tokens: {len(tokens)}, Elapsed: {elapsed:.2f}s (Speed: {len(tokens)/max(0.01, elapsed):.1f} tok/s)')
print('Generated text:\n', ''.join(tokens))
assert len(tokens) > 10, 'Streaming generation failed'
"
```

---

### 시나리오 4: 5대 종합 회귀 테스트 스위트 100% 통과 검증
```bash
docker exec oliview_chatbot_b python tests/run_all_regression_tests.py
```
* **기대 결과**: `ALL 5 REGRESSION TEST SUITES PASSED (100% SUCCESS)`.
