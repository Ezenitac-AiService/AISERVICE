"""sample_06_temperature.py
================================================================================
[6단계 실습] httpx 기반 샘플링 무작위성(Temperature=0.0 vs 2.0) 수치 제어 비교
================================================================================
학습 목표:
1. Temperature 수치(0.0 결정론적 vs 2.0 창의적 무작위)에 따른 생성 답변 문체의 다양성 및 독창성 변화를 실측합니다.
2. 추론 OFF(NO_THINK_SYSTEM_PROMPT) 및 추론 필터링 ON 환경에서 config.json의 default_max_tokens(1024 토큰)를 동적 적용하여 창의적 본문만 수신합니다.

실행 명령어:
    uv run python sample_06_temperature.py
"""

import time
from common import (
    check_server_health,
    load_sample_config,
    print_section_header,
    print_performance_summary,
    get_httpx_client,
    clean_think_tags,
    NO_THINK_SYSTEM_PROMPT
)

config = load_sample_config()
SERVER_HOST = config["server_host"]
MAIN_PORT = config["main_port"]
MODEL_NAME = config["default_model"]
TARGET_URL = f"{SERVER_HOST}:{MAIN_PORT}/v1/chat/completions"
PROMPT = "AI 서비스 개발의 가치를 표현하는 짧은 슬로건 3가지를 생성해 주세요."


def main():
    print_section_header("06. httpx Temperature (0.0 vs 2.0) 수치 비교 실습 (추론 OFF)")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    # -------------------------------------------------------------------------
    # [Part A] Temperature = 0.0 (결정론적, 정형화된 일관된 답변)
    # -------------------------------------------------------------------------
    print("▶️ [Part A] Temperature = 0.0 (결정론적 고정 답변) 요청 전송...")
    payload_a = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": NO_THINK_SYSTEM_PROMPT},
            {"role": "user", "content": PROMPT}
        ],
        "temperature": 0.0,
        "max_tokens": config["default_max_tokens"]
    }

    t_start_a = time.time()
    try:
        with get_httpx_client() as client:
            resp_a = client.post(TARGET_URL, json=payload_a, headers={"Connection": "close"})
            resp_a.raise_for_status()
            t_end_a = time.time()

            res_a = resp_a.json()
            raw_a = res_a["choices"][0]["message"]["content"] or ""
            clean_a = clean_think_tags(raw_a, show_think=False)
            gen_a = res_a.get("usage", {}).get("completion_tokens", 0)

            print(f"💬 [Part A: Temp 0.0 답변]:\n{clean_a}")
            print_performance_summary("Temp 0.0 (결정론적)", t_start_a, t_end_a, gen_tokens=gen_a)

    except Exception as err:
        print(f"❌ [Part A 실패]: {err}")

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part B] Temperature = 2.0 (창의적, 높은 무작위성 독창적 표현)
    # -------------------------------------------------------------------------
    print("▶️ [Part B] Temperature = 2.0 (창의적 다변화 답변) 요청 전송...")
    payload_b = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": NO_THINK_SYSTEM_PROMPT},
            {"role": "user", "content": PROMPT}
        ],
        "temperature": 2.0,
        "max_tokens": config["default_max_tokens"]
    }

    t_start_b = time.time()
    try:
        with get_httpx_client() as client:
            resp_b = client.post(TARGET_URL, json=payload_b, headers={"Connection": "close"})
            resp_b.raise_for_status()
            t_end_b = time.time()

            res_b = resp_b.json()
            raw_b = res_b["choices"][0]["message"]["content"] or ""
            clean_b = clean_think_tags(raw_b, show_think=False)
            gen_b = res_b.get("usage", {}).get("completion_tokens", 0)

            print(f"💬 [Part B: Temp 2.0 답변]:\n{clean_b}")
            print_performance_summary("Temp 2.0 (창의적 무작위)", t_start_b, t_end_b, gen_tokens=gen_b)

    except Exception as err:
        print(f"❌ [Part B 실패]: {err}")


if __name__ == "__main__":
    main()
