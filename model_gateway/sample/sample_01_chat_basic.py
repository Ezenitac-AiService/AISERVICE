"""sample_01_chat_basic.py
================================================================================
[1단계 실습] httpx 기반 LLM 기본 대화(Chat Completion) 라이브 API 호출
================================================================================
학습 목표:
1. REST API 클라이언트(httpx)를 사용하여 vllm_serv 메인 서버(포트 8081)에 기본 대화 요청을 전송합니다.
2. AI의 첫 번째 응답에서 모델이 내면에서 사고하는 과정(생각 과정 <think>)을 가시화(show_think=True)하여 관찰합니다.
3. config.json 중앙 설정의 default_max_tokens(1024 토큰)를 읽어와 생성 토큰 한도를 동적으로 적용합니다.

실행 명령어:
    uv run python sample_01_chat_basic.py
"""

import time
from common import (
    check_server_health,
    load_sample_config,
    print_section_header,
    print_performance_summary,
    get_httpx_client,
    clean_think_tags
)

config = load_sample_config()
SERVER_HOST = config["server_host"]
MAIN_PORT = config["main_port"]
MODEL_NAME = config["default_model"]
TARGET_URL = f"{SERVER_HOST}:{MAIN_PORT}/v1/chat/completions"
MAX_TOKENS = config["default_max_tokens"]  # config.json 중앙 설정값 로드


def main():
    print_section_header("01. httpx 규격 기본 대화(Chat Completion) 실습")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "당신은 IT 및 AI 기술 전문 어시스턴트입니다. 친절하게 답변해 주세요."},
            {"role": "user", "content": "vllm_serv 서버의 주요 장점을 1문장으로 요약해 주세요."}
        ],
        "temperature": config["default_temperature"],
        "max_tokens": MAX_TOKENS
    }

    t_start = time.time()
    try:
        with get_httpx_client() as client:
            resp = client.post(TARGET_URL, json=payload, headers={"Connection": "close"})
            resp.raise_for_status()
            t_end = time.time()

            res = resp.json()
            choice = res["choices"][0]
            raw_content = choice["message"]["content"] or ""
            
            # [1단계 핵심] 첫 대화 호출이므로 AI 생각 과정(<think>)을 시각적 박스로 표출 (show_think=True)
            clean_answer = clean_think_tags(raw_content, show_think=True)
            gen_tokens = res.get("usage", {}).get("completion_tokens", 0)
            reason = choice.get("finish_reason", "stop")

            print(f"\n{clean_answer}")
            print_performance_summary("httpx 기본 대화", t_start, t_end, gen_tokens=gen_tokens, finish_reason=reason)

    except Exception as err:
        print(f"❌ [01단계 호출 실패]: {err}")


if __name__ == "__main__":
    main()
