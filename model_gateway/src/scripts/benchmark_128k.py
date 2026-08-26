import os
import sys
import time
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.llama_manager import LlamaManager
from src.core.config import SUPPORTED_MODELS, MODELS_DIR

def get_peak_vram_mb() -> float:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", "0"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0

def run_128k_benchmark():
    print("=" * 70)
    print("  Gemma-4-2B (128K Context) 컨텍스트 길이에 따른 성능 벤치마크")
    print("  환경: NVIDIA GTX 1080 Ti (11GB VRAM)")
    print("=" * 70)

    from src.core.config_manager import ConfigManager
    cm = ConfigManager()
    model_id = cm.resolve_model_id("gemma4-e2b")
    config = SUPPORTED_MODELS.get(model_id)
    if config:
        config.n_ctx = 128000

    mgr = LlamaManager()
    print(f"🔄 모델 로드: {model_id} (n_ctx=128000)")
    load_res = mgr.load_model(model_id)
    vram_after_load = get_peak_vram_mb()
    print(f"   ✅ 로드 완료: {load_res['load_time_sec']:.2f}s | VRAM: {vram_after_load:.0f}MB\n")

    # 기본 문장 (약 100토큰 내외)
    base_text = (
        "양자 컴퓨팅은 양자역학의 원리를 이용하여 정보를 처리하는 새로운 패러다임의 컴퓨팅 기술입니다. "
        "기존의 고전적 컴퓨터가 비트(bit)를 사용하여 0 또는 1의 상태만을 표현하는 것과 달리, "
        "양자 컴퓨터는 큐비트(qubit)를 사용하여 0과 1의 상태를 동시에 표현할 수 있습니다. "
        "이를 중첩(superposition)이라 하며, 이 성질 덕분에 양자 컴퓨터는 특정 유형의 문제를 "
        "고전적 컴퓨터보다 기하급수적으로 빠르게 풀 수 있습니다. "
    )

    # 반복 횟수로 프롬프트 길이 조절 (어림잡은 토큰수)
    lengths = {
        "1K": 10,
        "4K": 40,
        "8K": 80,
        "16K": 160,
        "32K": 320,
        "64K": 640,
        "100K": 1000,
    }

    results = []

    for label, multiplier in lengths.items():
        prompt_text = base_text * multiplier + "\n\n위 내용을 세 줄로 요약해주세요."
        messages = [{"role": "user", "content": prompt_text}]
        
        print(f"   📝 테스트: {label} 입력 길이 프롬프트 (생성 중...)")
        
        try:
            start_gen = time.time()
            response = mgr.generate(messages, max_tokens=50, temperature=0.7)
            gen_time = time.time() - start_gen
            
            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            comp_tokens = usage.get("completion_tokens", 0)
            
            # TTFT와 TPOT 분리 측정은 현재 API 래퍼에서 정확히 불가하므로 전체 속도 측정
            tpot = (gen_time / comp_tokens * 1000) if comp_tokens > 0 else 0.0
            peak_vram = get_peak_vram_mb()

            print(f"      ✅ 입력 {prompt_tokens}tok -> 출력 {comp_tokens}tok | 소요시간: {gen_time:.2f}s | TPOT: {tpot:.1f}ms | VRAM: {peak_vram:.0f}MB")
            
            results.append({
                "label": label,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": comp_tokens,
                "time_sec": gen_time,
                "tpot_ms": tpot,
                "peak_vram_mb": peak_vram
            })
            
        except Exception as e:
            print(f"      ❌ 에러 발생 ({label}): {e}")

    print("\n" + "=" * 70)
    print("  📊 128K 확장 벤치마크 결과 요약")
    print("=" * 70)
    header = f"{'구간':<6} | {'입력 토큰':<10} | {'출력 토큰':<10} | {'소요시간(s)':<10} | {'TPOT(ms)':<10} | {'VRAM(MB)'}"
    print(header)
    print("─" * 70)
    for r in results:
        print(f"{r['label']:<6} | {r['prompt_tokens']:<10} | {r['completion_tokens']:<10} | {r['time_sec']:<10.2f} | {r['tpot_ms']:<10.1f} | {r['peak_vram_mb']:.0f}")

if __name__ == "__main__":
    run_128k_benchmark()
