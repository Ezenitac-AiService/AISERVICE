import gc
import json
import os
import sys
import time
from llama_cpp import Llama

def run_benchmark():
    print("=" * 70)
    print("🚀 GTX 1070 8GB 하드웨어 실측 정밀 벤치마크 (2B vs 4B 컨텍스트 & 성능) 🚀")
    print("=" * 70)
    
    test_prompt = "올리브영 20대 남성 스킨케어 인기 상품과 특징을 한국어로 요약해줘."
    results = {
        "2b_contexts": {},
        "4b_contexts": {},
        "2b_inference": {},
        "4b_inference": {},
        "model_swap": {}
    }

    # 1. Qwen 3.5 2B Context Scaling & Inference
    m2b_path = "/app/models/qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf"
    contexts_2b = [16384, 32768, 65536, 131072]
    
    print("\n[STEP 1] Qwen 3.5 2B 컨텍스트 한계 및 로드 시간 측정...")
    for ctx in contexts_2b:
        label = f"{ctx // 1024}K"
        t0 = time.perf_counter()
        try:
            llm = Llama(
                model_path=m2b_path,
                n_ctx=ctx,
                n_gpu_layers=999,
                verbose=False
            )
            load_time = time.perf_counter() - t0
            print(f"  ✅ 2B @ {label} ({ctx} tokens): 로드 성공 ({load_time:.2f}s)")
            results["2b_contexts"][label] = {"success": True, "load_time_s": round(load_time, 2)}
            
            # If 32K or 64K, run inference
            if ctx in (32768, 65536):
                print(f"    ▶ 2B @ {label} 실제 추론 벤치마크 (50 tokens)...")
                # Measure TTFT and Token Generation Speed
                t_infer_start = time.perf_counter()
                stream = llm.create_chat_completion(
                    messages=[{"role": "user", "content": test_prompt}],
                    max_tokens=50,
                    stream=True
                )
                first_token_time = None
                token_count = 0
                generated_text = ""
                for chunk in stream:
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        if first_token_time is None:
                            first_token_time = time.perf_counter() - t_infer_start
                        token_count += 1
                        generated_text += delta
                total_infer_time = time.perf_counter() - t_infer_start
                gen_time = total_infer_time - (first_token_time or 0)
                tps = (token_count - 1) / gen_time if gen_time > 0 and token_count > 1 else 0
                
                print(f"      - TTFT (첫 토큰 시간): {first_token_time*1000:.1f}ms")
                print(f"      - 생성 속도 (TPS): {tps:.2f} tokens/sec ({token_count} tokens in {total_infer_time:.2f}s)")
                results["2b_inference"][label] = {
                    "ttft_ms": round(first_token_time * 1000, 1),
                    "tps": round(tps, 2),
                    "total_time_s": round(total_infer_time, 2),
                    "sample": generated_text[:40] + "..."
                }
            
            del llm
            gc.collect()
            time.sleep(1)
        except Exception as e:
            print(f"  ❌ 2B @ {label} ({ctx} tokens): 실패 ({e})")
            results["2b_contexts"][label] = {"success": False, "error": str(e)}

    # 2. Qwen 3.5 4B Context Scaling & Inference
    m4b_path = "/app/models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf"
    contexts_4b = [8192, 16384, 24576, 32768, 49152]
    
    print("\n[STEP 2] Qwen 3.5 4B 컨텍스트 한계 및 로드 시간 측정...")
    for ctx in contexts_4b:
        label = f"{ctx // 1024}K"
        t0 = time.perf_counter()
        try:
            llm = Llama(
                model_path=m4b_path,
                n_ctx=ctx,
                n_gpu_layers=999,
                verbose=False
            )
            load_time = time.perf_counter() - t0
            print(f"  ✅ 4B @ {label} ({ctx} tokens): 로드 성공 ({load_time:.2f}s)")
            results["4b_contexts"][label] = {"success": True, "load_time_s": round(load_time, 2)}
            
            if ctx in (16384, 24576, 32768):
                print(f"    ▶ 4B @ {label} 실제 추론 벤치마크 (50 tokens)...")
                t_infer_start = time.perf_counter()
                stream = llm.create_chat_completion(
                    messages=[{"role": "user", "content": test_prompt}],
                    max_tokens=50,
                    stream=True
                )
                first_token_time = None
                token_count = 0
                generated_text = ""
                for chunk in stream:
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        if first_token_time is None:
                            first_token_time = time.perf_counter() - t_infer_start
                        token_count += 1
                        generated_text += delta
                total_infer_time = time.perf_counter() - t_infer_start
                gen_time = total_infer_time - (first_token_time or 0)
                tps = (token_count - 1) / gen_time if gen_time > 0 and token_count > 1 else 0
                
                print(f"      - TTFT (첫 토큰 시간): {first_token_time*1000:.1f}ms")
                print(f"      - 생성 속도 (TPS): {tps:.2f} tokens/sec ({token_count} tokens in {total_infer_time:.2f}s)")
                results["4b_inference"][label] = {
                    "ttft_ms": round(first_token_time * 1000, 1),
                    "tps": round(tps, 2),
                    "total_time_s": round(total_infer_time, 2),
                    "sample": generated_text[:40] + "..."
                }
            
            del llm
            gc.collect()
            time.sleep(1)
        except Exception as e:
            print(f"  ❌ 4B @ {label} ({ctx} tokens): 실패 ({e})")
            results["4b_contexts"][label] = {"success": False, "error": str(e)}

    # 3. Model Swap Latency (2B ➔ 4B ➔ 2B)
    print("\n[STEP 3] 모델 스왑 지연시간 (2B ➔ 4B, 4B ➔ 2B) 측정...")
    # Load 2B
    llm2 = Llama(model_path=m2b_path, n_ctx=32768, n_gpu_layers=999, verbose=False)
    time.sleep(0.5)
    
    # Swap to 4B (Unload 2B + Load 4B)
    t_swap1 = time.perf_counter()
    del llm2
    gc.collect()
    llm4 = Llama(model_path=m4b_path, n_ctx=16384, n_gpu_layers=999, verbose=False)
    swap1_time = time.perf_counter() - t_swap1
    print(f"  🔄 2B (32K) ➔ 4B (16K) 스왑 완료: {swap1_time:.2f}s")
    results["model_swap"]["2b_to_4b_s"] = round(swap1_time, 2)
    
    # Swap to 2B (Unload 4B + Load 2B)
    t_swap2 = time.perf_counter()
    del llm4
    gc.collect()
    llm2 = Llama(model_path=m2b_path, n_ctx=32768, n_gpu_layers=999, verbose=False)
    swap2_time = time.perf_counter() - t_swap2
    print(f"  🔄 4B (16K) ➔ 2B (32K) 스왑 완료: {swap2_time:.2f}s")
    results["model_swap"]["4b_to_2b_s"] = round(swap2_time, 2)
    del llm2
    gc.collect()

    print("\n" + "=" * 70)
    print("📊 벤치마크 JSON 데이터 요약:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("=" * 70)

if __name__ == "__main__":
    run_benchmark()
