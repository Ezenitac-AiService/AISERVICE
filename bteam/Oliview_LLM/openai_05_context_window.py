"""openai_05_context_window.py
================================================================================
[5단계 실습] OpenAI SDK 기반 맥락 토큰 제한(Context Window Limits) 추론 ON vs OFF 2단계 실측
================================================================================
학습 목표:
1. Part A (추론 ON): 생각 과정(<think>)이 생성 토큰 용량(512, 1024, benchmark_max_tokens=2048)을 먼저 소진하는 현상을 관찰하고 생각 과정을 표출합니다.
2. Part B (추론 OFF): NO_THINK_SYSTEM_PROMPT를 전송하여 100% 순수 답변 길이만으로 max_tokens 한도(128, 512, default_max_tokens=1024 - length vs stop)를 제어합니다.

실행 명령어:
    uv run python openai_05_context_window.py
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
PROMPT = "AI 서비스 아키텍처 설계 시 고려할 5가지 요소를 상세히 설명하세요."


def main():
    print_section_header("05. OpenAI SDK 토큰 용량 한도(Context Window) 추론 ON vs OFF 2단계 라이브 비교 (RTX 3060 12GB)")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    client = get_openai_client()

    # -------------------------------------------------------------------------
    # [Part A] SDK 추론 ON (Reasoning ON): 생각 과정이 max_tokens를 소진하는 현상 가시화 [512, 1024, benchmark_max_tokens]
    # -------------------------------------------------------------------------
    part_a_limits = [512, 1024, config["benchmark_max_tokens"]]
    print(f"▶️ [Part A] SDK 추론 ON 환경에서 max_tokens 설정별 생성 토큰 소진 실측 (생각 과정 표출, {part_a_limits})...\n")
    for limit in part_a_limits:
        print(f"⏱️  [Part A: SDK 추론 ON | max_tokens={limit}] 요청 전송 중...")
        t_start = time.time()
        try:
            comp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "당신은 IT 및 AI 기술 전문 어시스턴트입니다."},
                    {"role": "user", "content": PROMPT}
                ],
                temperature=0.3,
                max_tokens=limit
            )
            t_end = time.time()

            choice = comp.choices[0]
            raw_content = choice.message.content or ""
            clean_content = clean_think_tags(raw_content, show_think=True)
            reason = choice.finish_reason or "unknown"
            gen_tokens = comp.usage.completion_tokens if comp.usage else 0

            print(f"\n{clean_content}")
            print_performance_summary(f"Part A: SDK max_tokens={limit} (추론 ON)", t_start, t_end, gen_tokens=gen_tokens, finish_reason=reason)
            print("-" * 65)

        except Exception as err:
            print(f"❌ [Part A SDK max_tokens={limit} 실패]: {err}\n")

    # -------------------------------------------------------------------------
    # [Part B] SDK 추론 OFF (Reasoning OFF): 순수 답변 길이만으로 max_tokens 한도 제어 [128, 512, default_max_tokens]
    # -------------------------------------------------------------------------
    part_b_limits = [128, 512, config["default_max_tokens"]]
    print(f"\n▶️ [Part B] SDK 추론 OFF 환경에서 순수 답변 길이 한도 실측 (NO_THINK_SYSTEM_PROMPT 적용, {part_b_limits})...\n")
    for limit in part_b_limits:
        print(f"⏱️  [Part B: SDK 추론 OFF | max_tokens={limit}] 요청 전송 중...")
        t_start = time.time()
        try:
            comp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": NO_THINK_SYSTEM_PROMPT},
                    {"role": "user", "content": PROMPT}
                ],
                temperature=0.3,
                max_tokens=limit
            )
            t_end = time.time()

            choice = comp.choices[0]
            raw_content = choice.message.content or ""
            clean_content = clean_think_tags(raw_content, show_think=False)
            reason = choice.finish_reason or "unknown"
            gen_tokens = comp.usage.completion_tokens if comp.usage else 0

            print(f"\n💬 [Part B SDK 순수 답변 생성 출력 블록 (max_tokens={limit})]:")
            print("┌" + "─" * 63 + "┐")
            for line in clean_content.splitlines():
                print(f"│ {line}")
            print("└" + "─" * 63 + "┘")

            print_performance_summary(f"Part B: SDK max_tokens={limit} (추론 OFF)", t_start, t_end, gen_tokens=gen_tokens, finish_reason=reason)
            print("-" * 65)

        except Exception as err:
            print(f"❌ [Part B SDK max_tokens={limit} 실패]: {err}\n")


if __name__ == "__main__":
    main()
