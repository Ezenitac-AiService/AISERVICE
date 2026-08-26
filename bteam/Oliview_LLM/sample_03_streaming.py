"""sample_03_streaming.py
================================================================================
[3단계 실습] httpx 기반 실시간 스트리밍(SSE Streaming) 및 TTFT/TPS 측정 실습
================================================================================
학습 목표:
1. stream=True 설정으로 SSE(Server-Sent Events) 청크(Chunk) 데이터를 실시간 수신합니다.
2. config.json 중앙 설정의 default_max_tokens(1024 토큰)를 동적 적용하여 실시간 타자기 효과로 생각 과정과 완결 답변을 수신합니다.

실행 명령어:
    uv run python sample_03_streaming.py
"""

import time
import json
import sys
from common import (
    check_server_health,
    load_sample_config,
    print_section_header,
    print_performance_summary,
    get_httpx_client
)

config = load_sample_config()
SERVER_HOST = config["server_host"]
MAIN_PORT = config["main_port"]
MODEL_NAME = config["default_model"]
TARGET_URL = f"{SERVER_HOST}:{MAIN_PORT}/v1/chat/completions"
MAX_TOKENS = config["default_max_tokens"]


def main():
    print_section_header("03. httpx 실시간 스트리밍 및 TTFT/TPS 측정 실습")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "당신은 IT 및 AI 기술 전문 어시스턴트입니다."},
            {"role": "user", "content": "AI 개발자에게 필요한 3가지 핵심 역량을 요약해 주세요."}
        ],
        "temperature": 0.3,
        "max_tokens": MAX_TOKENS,
        "stream": True  # 스트리밍 활성화
    }

    t_start = time.time()
    t_first = None
    gen_tokens = 0
    full_content = ""

    print("💬 [httpx 실시간 스트리밍 응답 수신 중...]:\n")

    try:
        with get_httpx_client(timeout=180.0) as client:
            with client.stream("POST", TARGET_URL, json=payload, headers={"Connection": "close"}) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            choice = chunk["choices"][0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")

                            if content:
                                if t_first is None:
                                    t_first = time.time()  # 첫 번째 토큰 도착 시각 기록 (TTFT)

                                full_content += content
                                gen_tokens += 1

                                # 터미널에 실시간 텍스트 출력 (타자기 효과)
                                sys.stdout.write(content)
                                sys.stdout.flush()

                        except json.JSONDecodeError:
                            continue

        t_end = time.time()
        print("\n")
        print_performance_summary("httpx 실시간 스트리밍", t_start, t_end, t_first=t_first, gen_tokens=gen_tokens)

    except Exception as err:
        print(f"\n❌ [03단계 스트리밍 실패]: {err}")


if __name__ == "__main__":
    main()
