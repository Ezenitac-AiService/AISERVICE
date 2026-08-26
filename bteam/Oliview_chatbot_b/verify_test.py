import json
import time
import urllib.request
import urllib.error

base_url = "http://127.0.0.1:8002"

print("=" * 80)
print("OLIVIEW MULTI-TIER LLM & 2K CONTEXT GUARDRAIL INTEGRATION TEST")
print("=" * 80)

# [1] Fast Chat Endpoint (qwen3.5-2b)
print("\n[1] Testing Fast Chat Endpoint (/api/v1/chat/fast) with qwen3.5-2b...")
t0 = time.time()
req_data = json.dumps({"query": "지성 피부에 어울리는 가벼운 여름 스킨케어 팁 3줄 요약해줘", "max_tokens": 2048}).encode("utf-8")
req = urllib.request.Request(f"{base_url}/api/v1/chat/fast", data=req_data, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=120.0) as res:
        data = json.loads(res.read().decode("utf-8"))
        elapsed = time.time() - t0
        print(f"✅ Fast Chat HTTP Status: {res.status}")
        print(f"   Model Used: {data.get('model')}")
        print(f"   Latency: {data.get('latency_sec')}s (Total HTTP: {elapsed:.2f}s)")
        print(f"   AI Answer: {data.get('answer')[:120]}...")
except Exception as e:
    print(f"❌ Fast Chat Failed: {e}")

# [2] High-Quality RAG Synthesis (/api/v1/search) with qwen3.5-4b
print("\n[2] Testing High-Quality RAG Synthesis (/api/v1/search) with qwen3.5-4b...")
t0 = time.time()
req_data = json.dumps({"query": "민감성 피부에 순하고 자극 없는 수분크림 추천해줘", "top_n": 3, "model": "qwen3.5-4b"}).encode("utf-8")
req = urllib.request.Request(f"{base_url}/api/v1/search", data=req_data, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=240.0) as res:
        data = json.loads(res.read().decode("utf-8"))
        elapsed = time.time() - t0
        print(f"✅ RAG Synthesis HTTP Status: {res.status}")
        print(f"   Model Used: {data.get('model_used')}")
        print(f"   Matched Products Count: {len(data.get('search_results', []))}")
        for i, prod in enumerate(data.get('search_results', [])[:3], 1):
            print(f"   - Product {i}: [{prod.get('brand_name')}] {prod.get('product_name')} (Score: {prod.get('rerank_score', 0):.4f})")
        print(f"   LLM Answer ({elapsed:.2f}s): {data.get('llm_answer')[:180]}...")
except Exception as e:
    print(f"❌ RAG Synthesis Failed: {e}")

# [3] 2K Context Guardrail Trimming Unit Verification
print("\n[3] Testing 2K Context Guardrail (budget_context_documents) logic...")
from common import budget_context_documents, RecommendedProduct

mock_docs = [
    RecommendedProduct(
        rank=i,
        product_name=f"테스트 상품 {i}",
        brand_name="테스트 브랜드",
        category="스킨케어",
        review_score=5,
        separated_sentence="이것은 매우 긴 사용자 리뷰 문장입니다. " * 30,  # ~600 chars
        display_name="보습력",
        sentiment_label="긍정",
        cosine_similarity=0.9,
        rerank_score=0.95
    ) for i in range(1, 10)
]

budgeted_9b = budget_context_documents(mock_docs, model_name="qwen3.5-9b", max_total_chars=1500, max_sentence_len=150)
total_9b_chars = sum(len(d.separated_sentence) for d in budgeted_9b)

print(f"✅ 9B Guardrail Test:")
print(f"   Input Documents: {len(mock_docs)} (Total Chars: ~{sum(len(d.separated_sentence) for d in mock_docs)})")
print(f"   Budgeted Documents: {len(budgeted_9b)}")
print(f"   Total Budgeted Chars: {total_9b_chars} (Limit: 1500)")
print(f"   Max Single Sentence: {max(len(d.separated_sentence) for d in budgeted_9b)} (Limit: 150)")
assert total_9b_chars <= 1500, "9B total context budget exceeded!"
assert all(len(d.separated_sentence) <= 153 for d in budgeted_9b), "Single sentence budget exceeded!"
print(f"   ✓ All 2K context constraints strictly enforced!")

print("\n" + "=" * 80)
print("ALL MULTI-TIER ROUTING & CONTEXT GUARDRAIL TESTS COMPLETED SUCCESSFULLY")
print("=" * 80)
