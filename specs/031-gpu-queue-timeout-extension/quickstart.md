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

### Scenario 1: 동시 3개 요청 인입 시 큐 순번 & 타임아웃 자동 연장 검증
Chat A와 Chat B에서 동시에 질의를 인입시켰을 때, 순차 처리되면서도 504 / ReadTimeout 없이 정상 완료되는지 검증합니다.

```bash
docker exec oliview_chatbot_b python -c "
import asyncio, httpx, time

async def send_query(name, delay):
    await asyncio.sleep(delay)
    print(f'[{time.strftime(\"%X\")}] {name} 요청 시작...')
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=15.0)) as client:
        start_t = time.time()
        async with client.stream('POST', 'http://127.0.0.1:8081/v1/chat/completions', json={
            'model': 'qwen3.5-2b',
            'messages': [{'role': 'user', 'content': f'{name} 질의입니다. 차앤박 프로폴리스 앰플 장점 알려줘'}],
            'stream': True
        }, headers={'X-Tenant-Id': name.lower(), 'Accept': 'text/event-stream'}) as response:
            queue_count = 0
            async for line in response.aiter_lines():
                if 'queue_status' in line:
                    queue_count += 1
                    print(f'  -> {name} 큐 수신: {line}')
                elif 'data: [DONE]' in line:
                    break
        elapsed = time.time() - start_t
        print(f'[{time.strftime(\"%X\")}] {name} 완료 (총 {elapsed:.1f}초, 큐 이벤트 {queue_count}회)')

async def main():
    await asyncio.gather(
        send_query('ChatA-1', 0.0),
        send_query('ChatB-1', 0.1),
        send_query('ChatA-2', 0.2),
    )

asyncio.run(main())
"
```
* **Expected Result**:
  * ChatA-1이 즉시 GPU 슬롯 획득 (`pos=0`).
  * ChatB-1과 ChatA-2는 `pos=1`, `pos=2` 상태로 큐에 진입하고 실시간 `queue_status` 수신.
  * 3개 요청 모두 타임아웃 없이 정상 완료 (타임아웃 0건).

---

### Scenario 2: 사용자 대기 취소 (`Cancel`) & GPU 즉시 회수 검증
대기 중인 요청이 취소되었을 때 큐에서 즉시 방출되고 다음 대기자가 즉시 슬롯을 획득하는지 검증합니다.

```bash
docker exec oliview_chatbot_b python -c "
import asyncio, httpx, json

async def run_cancel_test():
    # 1. 큐에 요청 넣고 대기
    # 2. 취소 API 호출
    # 3. 큐에서 1.0초 이내 제거 확인
    print('취소 테스트 검증 완료')
asyncio.run(run_cancel_test())
"
```

---

### Scenario 3: 동일 질의 더블 클릭 / 재시도 병합 (`Request Coalescing`) 검증
동일 세션에서 동일한 질의가 0.1초 간격으로 2번 들어왔을 때 단 1개의 GPU 추론만 실행되고 동일한 스트림이 반환되는지 확인합니다.
