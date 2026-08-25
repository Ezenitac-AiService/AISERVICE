import urllib.request
import json
import time

def test_endpoint(name, url, payload):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode('utf-8')
            elapsed = time.perf_counter() - t0
            print(f"[{name}] SUCCESS ({elapsed*1000:.1f}ms): status={resp.status}, bytes={len(data)}")
            try:
                j = json.loads(data)
                if 'data' in j:
                    print(f"  -> data count: {len(j['data'])}")
                if 'results' in j:
                    print(f"  -> results count: {len(j['results'])}")
            except Exception:
                pass
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"[{name}] FAILED ({elapsed*1000:.1f}ms): {e}")

query = "차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘"
docs = [
    "수분을 채우는데 도움이 되는 앰플이어서 촉촉합니다.",
    "흡수력이 아주 우수하고 끈적이지 않아서 좋아요.",
    "피부 속까지 보습이 유지되는 느낌입니다.",
    "진정 효과는 조금 부족하지만 데일리로 쓰기 무난합니다.",
    "향이 강하지 않고 순해서 트러블 피부에도 괜찮았어요."
] * 5  # 25 docs

print("=== 1. EMBEDDING (8090) ===")
test_endpoint("BGE-M3 (8090)", "http://127.0.0.1:8090/v1/embeddings", {"model": "bge-m3", "input": [query] + docs})

print("\n=== 2. RERANKER (8091) ===")
test_endpoint("BGE-Reranker /v1/embeddings (8091)", "http://127.0.0.1:8091/v1/embeddings", {"model": "bge-reranker-v2-m3", "input": [query] + docs})
test_endpoint("BGE-Reranker /v1/rerank (8091)", "http://127.0.0.1:8091/v1/rerank", {"model": "bge-reranker-v2-m3", "query": query, "documents": docs})
test_endpoint("BGE-Reranker /rerank (8091)", "http://127.0.0.1:8091/rerank", {"model": "bge-reranker-v2-m3", "query": query, "documents": docs})

print("\n=== 3. LLM COMPLETION (8081) ===")
test_endpoint("Qwen (8081)", "http://127.0.0.1:8081/v1/chat/completions", {
    "model": "qwen3.5-2b",
    "messages": [{"role": "user", "content": "안녕하세요"}],
    "max_tokens": 10
})
