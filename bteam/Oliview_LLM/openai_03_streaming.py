"""openai_03_streaming.py
================================================================================
[3단계 실습] OpenAI SDK 실시간 스트리밍 및 TTFT/TPS 측정 실습
================================================================================
학습 목표:
1. OpenAI SDK client.chat.completions.create(stream=True) 파라미터를 사용하여 스트리밍 데이터를 수신합니다.
2. config.json 중앙 설정의 default_max_tokens(1024 토큰)를 동적 적용하여 실시간 타자기 효과로 생각 과정과 완결 답변을 수신합니다.

실행 명령어:
    uv run python openai_03_streaming.py
"""

import time
import sys
from common import (
    check_server_health,
    load_sample_config,
    print_section_header,
    print_performance_summary,
    get_openai_client
)

config = load_sample_config()
SERVER_HOST = config["server_host"]
MAIN_PORT = config["main_port"]
MODEL_NAME = config["default_model"]
MAX_TOKENS = config["default_max_tokens"]


def main():
    print_section_header("03. OpenAI SDK 실시간 스트리밍 및 TTFT/TPS 측정 실습")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    client = get_openai_client()

    print("💬 [SDK 실시간 스트리밍 응답 수신 중...]:\n")

    t_start = time.time()
    t_first = None
    gen_tokens = 0
    full_content = ""

    try:
        response_stream = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "당신은 IT 및 AI 기술 전문 어시스턴트입니다."},
                {"role": "user", "content": "AI 개발자에게 필요한 3가지 핵심 역량을 요약해 주세요."}
            ],
            temperature=0.3,
            max_tokens=MAX_TOKENS,
            stream=True  # 스트리밍 청크 활성화
        )

        for chunk in response_stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                content = delta.content or ""

                if content:
                    if t_first is None:
                        t_first = time.time()  # TTFT 측정 지점

                    full_content += content
                    gen_tokens += 1

                    # 터미널 실시간 출력
                    sys.stdout.write(content)
                    sys.stdout.flush()

        t_end = time.time()
        print("\n")
        print_performance_summary("OpenAI SDK 실시간 스트리밍", t_start, t_end, t_first=t_first, gen_tokens=gen_tokens)

    except Exception as err:
        print(f"\n❌ [SDK 스트리밍 실패]: {err}")


if __name__ == "__main__":
    main()
