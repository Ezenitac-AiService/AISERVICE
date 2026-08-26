"""openai_02_reasoning_control.py
================================================================================
[2단계 실습] OpenAI SDK 기반 추론 고찰(Reasoning <think>) ON vs OFF 대칭 성능 비교
================================================================================
학습 목표:
1. Part A (추론 ON - benchmark_max_tokens=2048): 생각 과정(<think>)을 가시화(show_think=True)하여 고찰 단계와 완결 답변을 확인합니다.
2. Part B (추론 OFF - no_think_max_tokens=512): NO_THINK_SYSTEM_PROMPT를 사용하여 생각 생성을 차단하고, 순수 답변만 즉시 수신할 때의 속도 향상(약 3.1배)을 체감합니다.

실행 명령어:
    uv run python openai_02_reasoning_control.py
"""

import time
from common import (
    check_server_health,
    load_sample_config,
    print_section_header,
    print_performance_summary,
    get_openai_client,
    clean_think_tags,
    NO_THINK_SYSTEM_PROMPT
)

config = load_sample_config()
SERVER_HOST = config["server_host"]
MAIN_PORT = config["main_port"]
MODEL_NAME = config["default_model"]
PROMPT = "GPU VRAM 오프로딩 기법에 대해 핵심 개념을 1문장으로 요약해 주세요."


def main():
    print_section_header("02. OpenAI SDK 추론 고찰(Reasoning) ON vs OFF 대칭 비교 실습")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    client = get_openai_client()

    # -------------------------------------------------------------------------
    # [Part A] SDK 추론 ON (Reasoning ON): 생각 과정 시각적 표출 (config["benchmark_max_tokens"] = 2048)
    # -------------------------------------------------------------------------
    print(f"▶️ [Part A] SDK 추론 ON 요청 전송 (생각 과정 표출, max_tokens={config['benchmark_max_tokens']})...")
    t_start_a = time.time()
    try:
        comp_a = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "당신은 IT 및 AI 기술 전문 어시스턴트입니다."},
                {"role": "user", "content": PROMPT}
            ],
            temperature=0.3,
            max_tokens=config["benchmark_max_tokens"]
        )
        t_end_a = time.time()

        choice_a = comp_a.choices[0]
        raw_a = choice_a.message.content or ""
        clean_a = clean_think_tags(raw_a, show_think=True)  # 생각 과정 가시화
        gen_a = comp_a.usage.completion_tokens if comp_a.usage else 0

        print(f"\n{clean_a}")
        perf_a = print_performance_summary("Part A: SDK 추론 ON", t_start_a, t_end_a, gen_tokens=gen_a, finish_reason=choice_a.finish_reason or "stop")

    except Exception as err:
        print(f"❌ [Part A SDK 실패]: {err}")
        return

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part B] SDK 추론 OFF (Reasoning OFF): 순수 답변 즉시 수신 (config["no_think_max_tokens"] = 512)
    # -------------------------------------------------------------------------
    print(f"▶️ [Part B] SDK 추론 OFF 요청 전송 (NO_THINK_SYSTEM_PROMPT 적용, max_tokens={config['no_think_max_tokens']})...")
    t_start_b = time.time()
    try:
        comp_b = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": NO_THINK_SYSTEM_PROMPT},  # 추론 전면 차단
                {"role": "user", "content": PROMPT}
            ],
            temperature=0.3,
            max_tokens=config["no_think_max_tokens"]
        )
        t_end_b = time.time()

        choice_b = comp_b.choices[0]
        raw_b = choice_b.message.content or ""
        clean_b = clean_think_tags(raw_b, show_think=False)  # 순수 답변만 추출
        gen_b = comp_b.usage.completion_tokens if comp_b.usage else 0

        print(f"\n💬 [Part B SDK 순수 답변]:\n{clean_b}")
        perf_b = print_performance_summary("Part B: SDK 추론 OFF", t_start_b, t_end_b, gen_tokens=gen_b, finish_reason=choice_b.finish_reason or "stop")

    except Exception as err:
        print(f"❌ [Part B SDK 실패]: {err}")
        return

    # -------------------------------------------------------------------------
    # [비교 분석 요약]
    # -------------------------------------------------------------------------
    speed_up = perf_a["total_elapsed"] / perf_b["total_elapsed"] if perf_b["total_elapsed"] > 0 else 0
    saved_tokens = perf_a["gen_tokens"] - perf_b["gen_tokens"]
    print(f"\n💡 [비교 결과 요약]:")
    print(f"   • SDK 추론 OFF 설정으로 응답 속도가 약 {speed_up:.1f}배 향상되었습니다!")
    print(f"   • 불필요한 고찰 토큰이 차단되어 약 {saved_tokens}개의 토큰 사용량이 절감되었습니다.")


if __name__ == "__main__":
    main()
