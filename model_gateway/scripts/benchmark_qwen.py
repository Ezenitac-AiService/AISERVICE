import json
import time
import urllib.request
import urllib.error

def test_streaming_inference(model_id: str, prompt: str, max_tokens: int = 150):
    url = "http://127.0.0.1:8081/v1/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a helpful and intelligent AI assistant. Respond in Korean."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": True
    }
    
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    
    start_time = time.perf_counter()
    first_token_time = None
    generated_text = ""
    token_count = 0
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            for line in response:
                line_str = line.decode("utf-8").strip()
                if not line_str or not line_str.startswith("data:"):
                    continue
                data_content = line_str[5:].strip()
                if data_content == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_content)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            if first_token_time is None:
                                first_token_time = time.perf_counter()
                            token_count += 1
                            generated_text += content
                except json.JSONDecodeError:
                    continue
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8')}"}
    except Exception as e:
        return {"error": str(e)}
        
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    ttft = (first_token_time - start_time) * 1000.0 if first_token_time else 0.0
    gen_time = (end_time - first_token_time) if first_token_time else total_time
    tok_per_sec = (token_count / gen_time) if gen_time > 0 else 0.0
    
    return {
        "model_id": model_id,
        "prompt": prompt,
        "generated_text": generated_text.strip(),
        "token_count": token_count,
        "ttft_ms": ttft,
        "total_time_s": total_time,
        "generation_time_s": gen_time,
        "tokens_per_sec": tok_per_sec
    }

def test_non_streaming_inference(model_id: str, prompt: str, max_tokens: int = 150):
    url = "http://127.0.0.1:8081/v1/chat/completions"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a helpful and intelligent AI assistant. Respond in Korean."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": False
    }
    
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8')}"}
    except Exception as e:
        return {"error": str(e)}
        
    end_time = time.perf_counter()
    total_time = end_time - start_time
    
    choices = res_data.get("choices", [])
    content = choices[0]["message"]["content"] if choices else ""
    usage = res_data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    prompt_tokens = usage.get("prompt_tokens", 0)
    
    tok_per_sec = (completion_tokens / total_time) if total_time > 0 and completion_tokens > 0 else 0.0
    
    return {
        "model_id": model_id,
        "prompt": prompt,
        "generated_text": content.strip(),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_time_s": total_time,
        "tokens_per_sec": tok_per_sec
    }

def main():
    prompts = [
        ("단답형 질의", "인공지능과 머신러닝의 차이점을 한 문장으로 명확하게 설명해줘."),
        ("창작 및 추론 질의", "파이썬으로 피보나치 수열을 구하는 제너레이터 함수 코드와 간단한 사용 예시를 작성해줘."),
        ("한국어 장문 생성", "대한민국의 사계절(봄, 여름, 가을, 겨울)의 특징과 각 계절의 아름다움을 소개하는 글을 3문장으로 작성해줘.")
    ]
    
    print("=" * 70)
    print("🚀 Qwen3.5 LLM 인퍼런스 속도 및 성능 벤치마크 테스트")
    print("=" * 70)
    
    # 1. 헬스 및 GPU 상태 확인
    try:
        with urllib.request.urlopen("http://127.0.0.1:8081/api/health", timeout=5) as res:
            health = json.loads(res.read().decode("utf-8"))
            print(f"📌 GPU 장치: {health.get('gpu_name', 'Unknown')}")
            print(f"📌 총 VRAM: {health.get('vram_total_mb')} MB | 여유 VRAM: {health.get('vram_free_mb')} MB")
            print(f"📌 활성 모델: {health.get('active_model')}")
    except Exception as e:
        print(f"⚠️ 헬스체크 확인 실패: {e}")
    print("-" * 70)
    
    results = []
    
    for idx, (label, p) in enumerate(prompts, 1):
        print(f"\n[테스트 {idx}/3] {label}")
        print(f"📝 프롬프트: \"{p}\"")
        print("⏳ 실시간 스트리밍 인퍼런스 수행 중...")
        
        res = test_streaming_inference("qwen3.5-4b", p, max_tokens=200)
        if "error" in res:
            print(f"❌ 에러 발생: {res['error']}")
            continue
            
        print(f"✅ 첫 토큰 생성 지연시간 (TTFT): {res['ttft_ms']:.2f} ms")
        print(f"⚡ 토큰 생성 속도: {res['tokens_per_sec']:.2f} tok/s")
        print(f"⏱️ 총 응답 소요 시간: {res['total_time_s']:.2f} 초 (생성 토큰: {res['token_count']} tokens)")
        print(f"💬 생성된 답변 요약:\n{res['generated_text'][:150]}...")
        print("-" * 70)
        results.append(res)
        
    print("\n" + "=" * 70)
    print("📊 최종 벤치마크 요약 결과")
    print("=" * 70)
    if results:
        avg_ttft = sum(r["ttft_ms"] for r in results) / len(results)
        avg_speed = sum(r["tokens_per_sec"] for r in results) / len(results)
        total_tokens = sum(r["token_count"] for r in results)
        print(f"• 평균 TTFT (Time to First Token): {avg_ttft:.2f} ms")
        print(f"• 평균 토큰 생성 속도 (Throughput): {avg_speed:.2f} tok/s")
        print(f"• 총 생성 토큰 수: {total_tokens} tokens")
    print("=" * 70)

if __name__ == "__main__":
    main()
