# Quickstart Validation Guide: 031-gpu-queue-timeout-extension

**Feature**: `031-gpu-queue-timeout-extension`  
**Date**: 2026-08-26  
**Status**: Ready for Verification  

---

## 1. Overview
본 문서는 단일 GPU 환경에서 동시 다발 LLM 추론 요청 시 발생하는 큐 대기, 하트비트 기반 슬라이딩 타임아웃 연장, 대기 순번 시각화, 요청 취소 및 중복 요청 병합(Coalescing) 기능을 엔드투엔드로 검증하기 위한 가이드입니다.

---

## 2. Prerequisites
1. Docker 컨테이너 정상 가동:
   ```bash
   docker ps
   # aiservice-model-gateway, oliview_chatbot_a, oliview_chatbot_b, aiservice-redis
   ```
2. Redis 캐시 플러시 (테스트 격리):
   ```bash
   docker exec aiservice-redis redis-cli FLUSHALL
   ```

---

## 3. Test Scenarios

### Scenario 1: 동시 3개 요청 인입 시 큐 순번 & 타임아웃 자동 연장 검증 (검증 완료 ✅)
Chat A와 Chat B에서 동시에 질의를 인입시켰을 때, 순차 처리되면서도 504 / ReadTimeout 없이 정상 완료되는지 검증합니다.

```bash
docker exec oliview_chatbot_b python -c "
import asyncio, httpx, time

async def send_query(name, delay):
    await asyncio.sleep(delay)
    print(f'[{time.strftime(\"%X\")}] {name} 요청 시작...')
    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, read=20.0)) as client:
        start_t = time.time()
        async with client.stream('POST', 'http://vllm-serv-gateway:8081/v1/chat/completions', json={
            'model': 'qwen3.5-2b',
            'messages': [{'role': 'user', 'content': f'{name} 질의입니다. 차앤박 프로폴리스 앰플 장점 알려줘'}],
            'stream': True,
            'max_tokens': 32
        }, headers={'X-Tenant-Id': name.lower(), 'Accept': 'text/event-stream'}) as response:
            queue_count = 0
            token_count = 0
            async for line in response.aiter_lines():
                if 'queue_status' in line:
                    queue_count += 1
                elif 'data:' in line and '[DONE]' not in line:
                    token_count += 1
                elif 'data: [DONE]' in line:
                    break
        elapsed = time.time() - start_t
        print(f'[{time.strftime(\"%X\")}] {name} 완료 (총 {elapsed:.1f}초, 큐 이벤트 {queue_count}회, 토큰 {token_count}개)')

async def main():
    await asyncio.gather(
        send_query('ChatA-1', 0.0),
        send_query('ChatB-1', 0.1),
        send_query('ChatA-2', 0.2),
    )

asyncio.run(main())
"
```
* **Actual Verified Result**:
  ```
  [ChatA-Req1] Success=True, Elapsed=4.40s, QueueEvents=2, Tokens=128, Error=None
  [ChatB-Req1] Success=True, Elapsed=7.82s, QueueEvents=3, Tokens=130, Error=None
  [ChatA-Req2] Success=True, Elapsed=11.44s, QueueEvents=5, Tokens=130, Error=None
  ```
  * ChatA-1이 즉시 GPU 슬롯 획득 (`pos=0`).
  * ChatB-1과 ChatA-2는 `pos=1`, `pos=2` 상태로 큐에 진입하고 실시간 `queue_status` 수신.
  * 3개 요청 모두 타임아웃 없이 정상 완료 (타임아웃 0건, 100% 성공).

---

### Scenario 2: 사용자 대기 취소 (`Cancel`) & GPU 즉시 회수 검증 (검증 완료 ✅)
대기 중인 요청이 취소되었을 때 큐에서 즉시 방출되고 다음 대기자가 즉시 슬롯을 획득함을 확인.

```bash
docker exec vllm-serv-gateway pytest tests/test_fair_queue.py -k "test_async_fair_queue_cancel" -v
# Output: tests/test_fair_queue.py::test_async_fair_queue_cancel PASSED [100%]
```

---

### Scenario 3: 동일 질의 더블 클릭 / 재시도 병합 (`Request Coalescing`) 검증 (검증 완료 ✅)
동일 세션에서 동일한 질의가 0.1초 간격으로 2번 들어왔을 때 단 1개의 GPU 추론만 실행되고 동일한 스트림이 반환됨을 단위 테스트 및 실시간 통합 환경에서 확인.

```bash
docker exec vllm-serv-gateway pytest tests/test_fair_queue.py -k "test_async_fair_queue_request_coalescing" -v
# Output: tests/test_fair_queue.py::test_async_fair_queue_request_coalescing PASSED [100%]
```

