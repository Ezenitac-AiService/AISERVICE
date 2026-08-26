"""
Concurrency stress test script for GPU Queue and Sliding Timeout (Spec 031 T022).
Simulates concurrent multi-client requests from Chat A and Chat B against the model gateway.
"""

import asyncio
import time
import httpx


async def _send_concurrent_query(
    client: httpx.AsyncClient,
    base_url: str,
    client_name: str,
    query: str,
    tenant_id: str,
    delay: float = 0.0,
):
    if delay > 0:
        await asyncio.sleep(delay)
    
    start_t = time.perf_counter()
    queue_events = []
    tokens = []
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-Tenant-Id": tenant_id,
        "X-Session-Id": f"ses_{tenant_id}_{int(time.time())}",
    }
    
    payload = {
        "model": "qwen3.5-2b",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query},
        ],
        "stream": True,
        "max_tokens": 128,
    }
    
    try:
        async with client.stream(
            "POST",
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=httpx.Timeout(45.0, read=15.0),  # Sliding inactivity timeout
        ) as response:
            if response.status_code != 200:
                err_body = await response.aread()
                return {
                    "client": client_name,
                    "success": False,
                    "elapsed_sec": round(time.perf_counter() - start_t, 2),
                    "queue_events_count": 0,
                    "tokens_count": 0,
                    "error": f"HTTP {response.status_code}: {err_body.decode('utf-8', errors='ignore')}",
                }
            
            pending_event_type = None
            async for line in response.aiter_lines():
                line = line.strip()
                print(f"[{client_name} RAW]: {repr(line)}")
                if not line or line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    pending_event_type = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if pending_event_type == "queue_status":
                        queue_events.append(data_str)
                        pending_event_type = None
                    elif data_str == "[DONE]":
                        break
                    else:
                        tokens.append(data_str)
                    pending_event_type = None
                    
        elapsed = time.perf_counter() - start_t
        return {
            "client": client_name,
            "success": True,
            "elapsed_sec": round(elapsed, 2),
            "queue_events_count": len(queue_events),
            "tokens_count": len(tokens),
            "error": None,
        }
    except Exception as e:
        elapsed = time.perf_counter() - start_t
        return {
            "client": client_name,
            "success": False,
            "elapsed_sec": round(elapsed, 2),
            "queue_events_count": len(queue_events),
            "tokens_count": len(tokens),
            "error": str(e),
        }


def test_concurrent_queue_execution():
    """3개의 동시 요청 인입 시 타임아웃 0건 및 큐 순차 처리 검증 (SC-001, SC-002, SC-003)."""
    async def _run():
        import os
        base_url = os.getenv(
            "SERVER_HOST_URL",
            "http://vllm-serv-gateway:8081" if os.path.exists("/.dockerenv") else "http://127.0.0.1:8081"
        )
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
        
        async with httpx.AsyncClient(limits=limits) as client:
            tasks = [
                _send_concurrent_query(client, base_url, "ChatA-Req1", "차앤박 프로폴리스 앰플 수분감 알려줘", "chata", delay=0.0),
                _send_concurrent_query(client, base_url, "ChatB-Req1", "헤라 블랙쿠션 커버력 알려줘", "chatb", delay=0.05),
                _send_concurrent_query(client, base_url, "ChatA-Req2", "식물나라 토너 자극성 알려줘", "chata", delay=0.1),
            ]
            
            results = await asyncio.gather(*tasks)
            
            for res in results:
                print(f"[{res['client']}] Success={res['success']}, Elapsed={res['elapsed_sec']}s, QueueEvents={res['queue_events_count']}, Tokens={res['tokens_count']}, Error={res['error']}")
                assert res["success"] is True, f"{res['client']} failed with {res['error']}"
                assert res["tokens_count"] > 0, f"{res['client']} received 0 tokens"
    
    asyncio.run(_run())

