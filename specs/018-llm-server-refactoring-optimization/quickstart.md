# Quickstart: 018-llm-server-refactoring-optimization

## 1. Quick Verification Commands

### 1) Check GPU Status & VRAM Headroom
```bash
nvidia-smi
```

### 2) Check Model Gateway Liveness & Readiness
```bash
curl http://localhost:8081/health/readiness
```

### 3) Benchmark TTFT with Prefix Caching
```bash
python -c "
import urllib.request, json, time
url = 'http://localhost:8081/v1/chat/completions'
payload = {
    'model': 'qwen3.5-4b',
    'messages': [
        {'role': 'system', 'content': '당신은 올리뷰 뷰티 리뷰 분석 AI 어시스턴트입니다.'},
        {'role': 'user', 'content': '수분감 좋은 앰플 추천해줘'}
    ],
    'max_tokens': 100,
    'stream': False
}
req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
t0 = time.perf_counter()
res = urllib.request.urlopen(req)
print('Latency:', f'{(time.perf_counter()-t0)*1000:.2f}ms')
"
```
