"""
성능 비교 벤치마크 스크립트.

3종의 Gemma-4 QAT 양자화 모델(E2B, E4B, 12B)을 실제로 로드하고,
Short / Medium / 4K Long 한국어 프롬프트를 주입하여
TPOT(Tokens Per Output Token)과 피크 VRAM 사용량을 측정합니다.

목업(Mock), 더미(Dummy), 스텁(Stub) 데이터는 일절 사용하지 않습니다.
"""
import os
import sys
import time
import subprocess
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.llama_manager import LlamaManager
from src.core.config import SUPPORTED_MODELS, MODELS_DIR

# ──────────────────────────────────────────────
# T008: 단계별 한국어 프롬프트 정의 (Short, Medium, 4K Long)
# ──────────────────────────────────────────────

PROMPTS = {
    "short": (
        "대한민국의 수도는 어디인가요? 간단히 답해주세요."
    ),
    "medium": (
        "인공지능의 역사를 1950년대 튜링 테스트부터 2020년대 대규모 언어 모델까지 "
        "시대별로 정리하여 핵심 사건, 주요 연구자, 그리고 각 시기의 기술적 한계를 "
        "포함하여 상세하게 설명해주세요. 또한 인공지능이 앞으로 사회에 미칠 영향에 "
        "대해서도 분석해주세요. 특히 의료, 교육, 법률, 예술 분야에서의 활용 가능성과 "
        "윤리적 고려사항을 함께 다뤄주세요."
    ),
    "long": (
        # 4K 컨텍스트를 채우기 위해 긴 텍스트를 구성합니다.
        # 실제 한국어 텍스트로 약 2000자 이상의 프롬프트를 생성합니다.
        "다음 주제에 대해 가능한 한 상세하게 답변해주세요.\n\n"
        "제1장: 양자 컴퓨팅의 기초\n"
        "양자 컴퓨팅은 양자역학의 원리를 이용하여 정보를 처리하는 새로운 패러다임의 컴퓨팅 기술입니다. "
        "기존의 고전적 컴퓨터가 비트(bit)를 사용하여 0 또는 1의 상태만을 표현하는 것과 달리, "
        "양자 컴퓨터는 큐비트(qubit)를 사용하여 0과 1의 상태를 동시에 표현할 수 있습니다. "
        "이를 중첩(superposition)이라 하며, 이 성질 덕분에 양자 컴퓨터는 특정 유형의 문제를 "
        "고전적 컴퓨터보다 기하급수적으로 빠르게 풀 수 있습니다.\n\n"
        "제2장: 양자 얽힘과 양자 게이트\n"
        "양자 얽힘(entanglement)은 두 개 이상의 큐비트가 서로 강하게 상관관계를 가지는 현상입니다. "
        "한 큐비트의 상태를 측정하면 다른 큐비트의 상태가 즉시 결정되며, 이는 아무리 먼 거리에서도 성립합니다. "
        "양자 게이트는 큐비트에 대한 연산을 수행하는 기본 단위로, 하다마드 게이트(Hadamard gate), "
        "CNOT 게이트, 파울리 게이트(X, Y, Z) 등이 있습니다. 이러한 게이트들의 조합으로 "
        "양자 회로(quantum circuit)를 구성하여 복잡한 양자 알고리즘을 실행할 수 있습니다.\n\n"
        "제3장: 양자 알고리즘의 응용\n"
        "쇼어 알고리즘(Shor's algorithm)은 대수 인수분해 문제를 다항 시간에 풀 수 있는 양자 알고리즘으로, "
        "현재 널리 사용되는 RSA 암호화 체계의 안전성에 직접적인 위협이 됩니다. "
        "그로버 알고리즘(Grover's algorithm)은 비정렬 데이터베이스에서 특정 항목을 검색하는 속도를 "
        "제곱근 수준으로 향상시키는 알고리즘입니다. 또한 양자 시뮬레이션은 분자 구조와 화학 반응을 "
        "정밀하게 모델링할 수 있어, 신약 개발과 재료 과학 분야에서 혁신적인 발전을 이끌 것으로 기대됩니다.\n\n"
        "제4장: 한국의 양자 기술 발전\n"
        "대한민국은 양자 기술 분야에서 적극적인 투자와 연구를 진행하고 있습니다. "
        "한국과학기술원(KAIST), 서울대학교, 한국표준과학연구원(KRISS) 등에서 "
        "양자 컴퓨팅, 양자 통신, 양자 센서 분야의 핵심 기술을 개발하고 있으며, "
        "정부는 양자 기술 육성 종합계획을 수립하여 2030년까지 세계 4대 양자 기술 강국 "
        "진입을 목표로 하고 있습니다. 삼성전자, SK텔레콤, KT 등 민간 기업들도 "
        "양자 암호 통신과 양자 컴퓨팅 플랫폼 개발에 참여하고 있습니다.\n\n"
        "위 네 개 장에 대해 각 장별로 핵심 개념을 요약하고, "
        "양자 컴퓨팅이 향후 10년간 사회에 미칠 영향을 전망해주세요."
    ),
}


# ──────────────────────────────────────────────
# T010: VRAM 측정 (nvidia-smi 서브프로세스 활용)
# ──────────────────────────────────────────────

def get_peak_vram_mb() -> float:
    """nvidia-smi를 호출하여 현재 GPU 0의 VRAM 사용량(MB)을 반환합니다."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
                "-i", "0",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0.0


# ──────────────────────────────────────────────
# T009, T011, T012: BenchmarkRunner
# ──────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """개별 모델 + 프롬프트에 대한 벤치마크 결과."""
    model_id: str
    prompt_type: str
    load_time_sec: float = 0.0
    tpot_ms: float = 0.0
    peak_vram_mb: float = 0.0
    completion_tokens: int = 0
    status: str = "SUCCESS"
    error_message: str = ""


def run_benchmark():
    """모든 모델과 프롬프트 조합에 대해 순차적으로 벤치마크를 수행합니다."""
    print("=" * 70)
    print("  Gemma-4 QAT 양자화 모델 성능 비교 벤치마크")
    print("  환경: NVIDIA GTX 1080 Ti (11GB VRAM)")
    print("=" * 70)

    from src.core.config_manager import ConfigManager
    cm = ConfigManager()
    catalog = cm.get_model_catalog()
    model_ids = [mid for mid in catalog.keys() if mid.startswith("gemma4")]
    prompt_types = ["short", "medium", "long"]
    results: List[BenchmarkResult] = []

    for model_id in model_ids:
        # 모델 디렉토리 존재 확인
        cfg = cm.get_model_config(model_id)
        rel_target = cfg.get("target_dir", f"models/{model_id}") if cfg else f"models/{model_id}"
        model_dir = cm.get_absolute_path(rel_target) or os.path.join(MODELS_DIR, model_id)
        if not os.path.isdir(model_dir):
            print(f"\n⚠️  {model_id}: 모델 디렉토리 없음 → 건너뜁니다.")
            for pt in prompt_types:
                results.append(BenchmarkResult(
                    model_id=model_id, prompt_type=pt,
                    status="SKIPPED", error_message="Model directory not found"
                ))
            continue

        gguf_files = [f for f in os.listdir(model_dir) if f.endswith(".gguf")]
        if not gguf_files:
            print(f"\n⚠️  {model_id}: .gguf 파일 없음 → 건너뜁니다.")
            for pt in prompt_types:
                results.append(BenchmarkResult(
                    model_id=model_id, prompt_type=pt,
                    status="SKIPPED", error_message="No .gguf file"
                ))
            continue

        # ── T009: 모델 로드 ──
        print(f"\n{'─' * 70}")
        print(f"🔄 모델 로드: {model_id}")
        mgr = LlamaManager()
        try:
            load_res = mgr.load_model(model_id)
            load_time = load_res.get("load_time_sec", 0.0)
            vram_after_load = get_peak_vram_mb()
            print(f"   ✅ 로드 완료: {load_time:.2f}s | VRAM: {vram_after_load:.0f}MB")
        except Exception as e:
            # ── T012: OOM 또는 로드 에러 처리 ──
            error_msg = str(e)
            is_oom = "out of memory" in error_msg.lower() or "cuda" in error_msg.lower()
            status = "OOM_FAILED" if is_oom else "LOAD_FAILED"
            print(f"   ❌ 로드 실패 ({status}): {error_msg}")
            for pt in prompt_types:
                results.append(BenchmarkResult(
                    model_id=model_id, prompt_type=pt,
                    status=status, error_message=error_msg
                ))
            continue

        # ── T011: 프롬프트별 TPOT 측정 ──
        for prompt_type in prompt_types:
            prompt_text = PROMPTS[prompt_type]
            messages = [{"role": "user", "content": prompt_text}]
            print(f"   📝 프롬프트: {prompt_type} ({len(prompt_text)}자)...", end=" ", flush=True)

            try:
                vram_before = get_peak_vram_mb()
                start_gen = time.time()
                response = mgr.generate(messages, max_tokens=100, temperature=0.7)
                gen_time = time.time() - start_gen
                vram_after = get_peak_vram_mb()

                tokens = response.get("usage", {}).get("completion_tokens", 0)
                tpot = (gen_time / tokens * 1000) if tokens > 0 else 0.0
                peak_vram = max(vram_after_load, vram_after)

                print(f"✅ {tokens}tok / {gen_time:.2f}s / TPOT={tpot:.1f}ms / VRAM={peak_vram:.0f}MB")
                results.append(BenchmarkResult(
                    model_id=model_id,
                    prompt_type=prompt_type,
                    load_time_sec=load_time,
                    tpot_ms=round(tpot, 2),
                    peak_vram_mb=round(peak_vram, 1),
                    completion_tokens=tokens,
                    status="SUCCESS",
                ))
            except Exception as e:
                error_msg = str(e)
                is_oom = "out of memory" in error_msg.lower() or "cuda" in error_msg.lower()
                status = "OOM_FAILED" if is_oom else "GEN_FAILED"
                print(f"❌ {status}: {error_msg}")
                results.append(BenchmarkResult(
                    model_id=model_id,
                    prompt_type=prompt_type,
                    load_time_sec=load_time,
                    peak_vram_mb=get_peak_vram_mb(),
                    status=status,
                    error_message=error_msg,
                ))

        # 모델 해제하여 다음 모델을 위한 VRAM 확보
        del mgr

    # ── 결과 요약 테이블 출력 ──
    print("\n" + "=" * 70)
    print("  📊 벤치마크 결과 요약")
    print("=" * 70)
    header = f"{'모델ID':<14} | {'프롬프트':<8} | {'상태':<12} | {'로드(s)':<8} | {'TPOT(ms)':<9} | {'VRAM(MB)':<9} | {'토큰수':<6}"
    print(header)
    print("─" * 70)
    for r in results:
        tpot_str = f"{r.tpot_ms:.1f}" if r.status == "SUCCESS" else "N/A"
        vram_str = f"{r.peak_vram_mb:.0f}" if r.peak_vram_mb > 0 else "N/A"
        tok_str = str(r.completion_tokens) if r.status == "SUCCESS" else "N/A"
        load_str = f"{r.load_time_sec:.2f}" if r.load_time_sec > 0 else "N/A"
        print(f"{r.model_id:<14} | {r.prompt_type:<8} | {r.status:<12} | {load_str:<8} | {tpot_str:<9} | {vram_str:<9} | {tok_str:<6}")

    # ── 최적 모델 추천 ──
    successful = [r for r in results if r.status == "SUCCESS"]
    if successful:
        print("\n" + "─" * 70)
        # 모델별로 평균 TPOT 계산
        model_avgs = {}
        for r in successful:
            if r.model_id not in model_avgs:
                model_avgs[r.model_id] = {"tpot_sum": 0, "count": 0, "max_vram": 0}
            model_avgs[r.model_id]["tpot_sum"] += r.tpot_ms
            model_avgs[r.model_id]["count"] += 1
            model_avgs[r.model_id]["max_vram"] = max(model_avgs[r.model_id]["max_vram"], r.peak_vram_mb)

        for mid, stats in model_avgs.items():
            avg_tpot = stats["tpot_sum"] / stats["count"]
            vram_margin = 11264 - stats["max_vram"]  # 11GB = 11264MB
            print(f"  📌 {mid}: 평균 TPOT={avg_tpot:.1f}ms, 최대 VRAM={stats['max_vram']:.0f}MB, VRAM 여유={vram_margin:.0f}MB")

        best = min(model_avgs.items(), key=lambda x: x[1]["tpot_sum"] / x[1]["count"])
        print(f"\n  🏆 추천 모델: {best[0]} (평균 TPOT={best[1]['tpot_sum']/best[1]['count']:.1f}ms)")
    else:
        print("\n  ⚠️ 성공한 벤치마크가 없습니다.")

    # JSON 결과 파일 저장
    results_path = os.path.join(MODELS_DIR, "..", "benchmark_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
    print(f"\n  💾 결과 저장: {os.path.abspath(results_path)}")


if __name__ == "__main__":
    run_benchmark()
