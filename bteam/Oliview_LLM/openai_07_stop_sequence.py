"""openai_07_stop_sequence.py
================================================================================
[7단계 실습] OpenAI SDK 기반 Stop Sequence ('2)') 감지 및 조기 중단 비교 실습
================================================================================
학습 목표:
1. OpenAI SDK client.chat.completions.create(stop=...) 파라미터를 사용하여 생성을 조기 중단시킵니다.
2. [중요 백엔드 설정] 추론 토큰량이 많아 생성 도중 한도에 도달하지 않도록 config.json의 benchmark_max_tokens(2048 토큰 = 2K)를 동적으로 적용하여 중단 토큰을 수신합니다.
3. 추론 필터링 ON 환경에서 Part A (전체 응답) vs Part B (조기 중단 응답)의 생성 토큰 수와 소요 시간을 비교합니다.

실행 명령어:
    uv run python openai_07_stop_sequence.py
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
PROMPT = "AI 서비스 성능 최적화 방법 3가지를 번호(1), 2), 3))를 붙여 항목별로 설명하세요."


def main():
    print_section_header("07. OpenAI SDK Stop Sequence ('2)') 감지 및 조기 중단 비교 실습")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    client = get_openai_client()

    # -------------------------------------------------------------------------
    # [Part A] SDK Stop 미지정: 1번, 2번, 3번 전체 작성 (config["benchmark_max_tokens"] = 2048)
    # -------------------------------------------------------------------------
    print("▶️ [Part A] SDK Stop 미지정 요청 전송 (1번, 2번, 3번 전체 답변 작성)...")
    t_start_a = time.time()
    try:
        comp_a = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": NO_THINK_SYSTEM_PROMPT},  # 추론 필터링 ON
                {"role": "user", "content": PROMPT}
            ],
            temperature=0.3,
            max_tokens=config["benchmark_max_tokens"]  # 2K 비교 공간 확보
        )
        t_end_a = time.time()

        raw_a = comp_a.choices[0].message.content or ""
        clean_a = clean_think_tags(raw_a, show_think=False)  # 추론 필터링 ON
        gen_a = comp_a.usage.completion_tokens if comp_a.usage else 0

        print(f"💬 [Part A SDK 일반 전체 답변]:\n{clean_a}")
        m_a = print_performance_summary("SDK Stop 미지정 (전체 완료)", t_start_a, t_end_a, gen_tokens=gen_a)

    except Exception as err:
        print(f"❌ [Part A SDK 실패]: {err}")
        return

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part B] SDK Stop ['\n2)', '2)'] 지정: 2번 작성 직전 감지 시 생성을 조기 중단
    # -------------------------------------------------------------------------
    print("▶️ [Part B] SDK Stop ['\\n2)', '2)'] 지정 요청 전송 (2번 시작 직후 감지 시 조기 중단)...")
    t_start_b = time.time()
    try:
        comp_b = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": NO_THINK_SYSTEM_PROMPT},  # 추론 필터링 ON
                {"role": "user", "content": PROMPT}
            ],
            temperature=0.3,
            stop=["\n2)", "2)"],  # 조기 중단 토큰 지정
            max_tokens=config["benchmark_max_tokens"]
        )
        t_end_b = time.time()

        raw_b = comp_b.choices[0].message.content or ""
        clean_b = clean_think_tags(raw_b, show_think=False)  # 추론 필터링 ON
        gen_b = comp_b.usage.completion_tokens if comp_b.usage else 0

        print(f"💬 [Part B SDK Stop 감지 조기 중단 답변]:\n{clean_b}")
        m_b = print_performance_summary("SDK Stop ['\\n2)', '2)'] 지정 (조기 중단)", t_start_b, t_end_b, gen_tokens=gen_b)

    except Exception as err:
        print(f"❌ [Part B SDK 실패]: {err}")
        return

    # -------------------------------------------------------------------------
    # [비교 분석 요약]
    # -------------------------------------------------------------------------
    saved_tokens = m_a["gen_tokens"] - m_b["gen_tokens"]
    print(f"\n💡 [비교 결과 요약]:")
    print(f"   • Part A (Stop 미지정): 1번, 2번, 3번 전체 작성 ({m_a['gen_tokens']}토큰 생성)")
    print(f"   • Part B (Stop 지정  ): 1번 작성 후 '2)' 시작 직후 생성을 조기 중단 ({saved_tokens}토큰 절감 생성)")


if __name__ == "__main__":
    main()
