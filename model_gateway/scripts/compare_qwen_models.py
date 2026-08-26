import json
import time
import urllib.request
import urllib.error

def benchmark_model(model_id: str):
    print("\n" + "=" * 65)
    print(f"🚀 [{model_id}] 벤치마크 테스트 시작 (Hot-Swap 적용)")
    print("=" * 65)
    
    # 1. Hot-swap / Apply model
    apply_req = urllib.request.Request(
        "http://127.0.0.1:8081/dashboard/api/apply",
        data=json.dumps({"model_id": model_id, "n_ctx": 4096}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Admin-Secret": "aiservice"}
    )
    try:
        with urllib.request.urlopen(apply_req, timeout=10) as res:
            pass
    except Exception as e:
        print(f"Apply error: {e}")
    
    # Wait for READY
    for attempt in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8081/dashboard/api/status", timeout=3) as res:
                data = json.loads(res.read().decode("utf-8"))
                if data.get("state") == "READY" and data.get("current_model") == model_id:
                    print(f"✅ {model_id} 로드 완료 (상태: READY)")
                    break
        except Exception:
            pass
        time.sleep(1)
        
    prompts = [
        ("단답형 요약", "인공지능과 머신러닝의 차이점을 한 문장으로 명확하게 설명해줘.", 80),
        ("코드 생성", "파이썬으로 피보나치 수열을 구하는 제너레이터 함수 코드를 작성해줘.", 150),
        ("한국어 장문", "대한민국의 사계절 특징과 각 계절의 아름다움을 소개하는 글을 3문장으로 작성해줘.", 200)
    ]
    
    model_results = []
    
    for label, prompt, max_tok in prompts:
        url = "http://127.0.0.1:8081/v1/chat/completions"
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": "You are a helpful and intelligent AI assistant. Respond in Korean."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tok,
            "temperature": 0.7,
            "stream": True
        }
        
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        
        start_time = time.perf_counter()
        first_token_time = None
        token_count = 0
        generated_text = ""
        
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
                except Exception:
                    continue
                    
        end_time = time.perf_counter()
        total_time = end_time - start_time
        ttft = (first_token_time - start_time) * 1000.0 if first_token_time else 0.0
        gen_time = (end_time - first_token_time) if first_token_time else total_time
        speed = (token_count / gen_time) if gen_time > 0 else 0.0
        
        print(f"[{label}] TTFT: {ttft:.1f}ms | 생성 속도: {speed:.2f} tok/s | 총 소요시간: {total_time:.2f}s | 토큰: {token_count}")
        model_results.append({
            "label": label,
            "ttft_ms": ttft,
            "speed_tok_s": speed,
            "total_time_s": total_time,
            "tokens": token_count,
            "preview": generated_text[:80].replace("\n", " ")
        })
        
    avg_ttft = sum(r["ttft_ms"] for r in model_results) / len(model_results)
    avg_speed = sum(r["speed_tok_s"] for r in model_results) / len(model_results)
    print(f"📊 [{model_id}] 평균 성능 -> TTFT: {avg_ttft:.1f}ms | 생성 속도: {avg_speed:.2f} tok/s")
    
    return {
        "model_id": model_id,
        "avg_ttft_ms": avg_ttft,
        "avg_speed_tok_s": avg_speed,
        "results": model_results
    }

def main():
    print("=" * 70)
    print("🏎️ Qwen3.5 시리즈 모델별 인퍼런스 속도 및 응답 성능 실측 벤치마크")
    print("=" * 70)
    
    res_2b = benchmark_model("qwen3.5-2b")
    res_4b = benchmark_model("qwen3.5-4b")
    
    print("\n" + "=" * 70)
    print("🏆 [최종 종합 비교 결과]")
    print("=" * 70)
    print(f"• Qwen 3.5 2B (경량 모델, 1.6GB) : 평균 TTFT {res_2b['avg_ttft_ms']:.1f} ms | 평균 속도 {res_2b['avg_speed_tok_s']:.2f} tok/s")
    print(f"• Qwen 3.5 4B (표준 모델, 2.8GB) : 평균 TTFT {res_4b['avg_ttft_ms']:.1f} ms | 평균 속도 {res_4b['avg_speed_tok_s']:.2f} tok/s")
    print("=" * 70)

if __name__ == "__main__":
    main()
