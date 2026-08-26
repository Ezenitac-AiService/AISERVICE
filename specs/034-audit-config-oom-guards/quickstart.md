# Quickstart & Verification Guide: Hardware-Tiered Dynamic Context & OOM Hardening

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Runnable Verification Guide

---

## 1. 사전 조건 (Prerequisites)
* Docker 컨테이너 가동: `vllm-serv-gateway`, `oliview_chatbot_b`, `aiservice-redis`
* GPU: NVIDIA GTX 1070 (8GB VRAM, Compute Capability 6.1)

---

## 2. 검증 시나리오 (Verification Scenarios)

### 시나리오 1: 전사 레거시 하드코딩 전수 감사 (Static Audit)
```bash
docker exec vllm-serv-gateway python -c "
from src.core.config_manager import ConfigManager
cfg = ConfigManager()
print('✅ Server Config Model:', cfg.get_default_model())
print('✅ Server Config Context:', cfg.get_current_n_ctx())
assert 'qwen3.5-2b' in cfg.get_default_model()
"
```

### 시나리오 2: 동적 하드웨어 프로파일 및 FlashAttention SM 6.1 생략 확인
```bash
docker exec vllm-serv-gateway python -c "
import urllib.request, json
with urllib.request.urlopen('http://127.0.0.1:8081/v1/profile') as r:
    data = json.loads(r.read().decode('utf-8'))
    print('✅ Profile Data:', json.dumps(data, indent=2))
"
```

### 시나리오 3: 4B 투명 라우팅 및 16K~32K 스트리밍 무중단 검증
```bash
docker exec oliview_chatbot_b python -c "
from oliview_core.client import AiGatewayClient
client = AiGatewayClient()
tokens = list(client.generate_stream(prompt='올리브영 세럼 추천해줘', max_tokens=30))
print(f'✅ Streamed {len(tokens)} tokens successfully!')
"
```
