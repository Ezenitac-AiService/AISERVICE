"""sample_10_structured_output.py
================================================================================
[10단계 실습] httpx 기반 Pydantic v2 단일 구조화 출력 3단계 제어 비교 (Part A / B / C)
================================================================================
학습 목표:
1. Pydantic v2(BaseModel) 클래스를 정의하고 .model_json_schema()를 생성하여 LLM에 전달합니다.
2. 3단계 구조화 출력을 비교합니다:
   - Part A: 일반 구조화 요청 (Strict JSON 포맷 유도, benchmark_max_tokens=2048)
   - Part B: 수신 응답 내 추론 태그 세척 (Reasoning Filtered, benchmark_max_tokens=2048)
   - Part C: 추론 OFF (NO_THINK_SYSTEM_PROMPT) + 세척으로 100% Pure JSON만 보장 (no_think_max_tokens=512)

실행 명령어:
    uv run python sample_10_structured_output.py
"""

import time
import json
from pydantic import BaseModel, Field
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


class StockSentiment(BaseModel):
    speaker: str = Field(description="작성자 닉네임")
    stock_name: str = Field(description="정식 종목명 (예: 삼성전자)")
    sentiment: str = Field(description="긍정, 부정, 중립 중 하나")


def main():
    print_section_header("10. httpx Pydantic v2 단일 구조화 출력 3단계(Part A / B / C) 비교 실습")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    schema_str = json.dumps(StockSentiment.model_json_schema(), ensure_ascii=False, indent=2)
    comment = "개미왕: 삼전 시외 급등하길래 바로 풀매수 쳤습니다."

    # -------------------------------------------------------------------------
    # [Part A] 일반 구조화 요청 (생각 태그 미정제 원본 수신, benchmark_max_tokens=2048)
    # -------------------------------------------------------------------------
    print("▶️ [Part A] 일반 구조화 요청 전송 (생각 과정 미정제 원본 수신)...")
    payload_a = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": f"다음 JSON Schema 규격을 반드시 준수하세요:\n{schema_str}"},
            {"role": "user", "content": comment}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": config["benchmark_max_tokens"]
    }

    t_start_a = time.time()
    try:
        with get_httpx_client() as client:
            resp_a = client.post(TARGET_URL, json=payload_a, headers={"Connection": "close"})
            resp_a.raise_for_status()
            t_end_a = time.time()
            res_a = resp_a.json()
            raw_a = res_a["choices"][0]["message"]["content"] or ""

            print(f"💬 [Part A 원본 응답]:\n{raw_a}")
            m_a = print_performance_summary("Part A: 일반 구조화 요청", t_start_a, t_end_a, gen_tokens=res_a.get("usage", {}).get("completion_tokens", 0))

    except Exception as err:
        print(f"❌ [Part A 실패]: {err}")

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part B] 추론 필터링 적용 (생각 태그 세척 후 Pydantic 파싱, benchmark_max_tokens=2048)
    # -------------------------------------------------------------------------
    print("▶️ [Part B] 추론 필터링 적용 요청 전송 (생각 태그 세척 후 Pydantic 검증)...")
    t_start_b = time.time()
    try:
        with get_httpx_client() as client:
            resp_b = client.post(TARGET_URL, json=payload_a, headers={"Connection": "close"})
            resp_b.raise_for_status()
            t_end_b = time.time()
            res_b = resp_b.json()
            raw_b = res_b["choices"][0]["message"]["content"] or ""
            clean_b = clean_think_tags(raw_b, show_think=False)

            parsed_b = StockSentiment.model_validate_json(clean_b)
            print(f"✅ [Part B Pydantic 검증 객체]: {parsed_b}")
            m_b = print_performance_summary("Part B: 추론 필터링 적용", t_start_b, t_end_b, gen_tokens=res_b.get("usage", {}).get("completion_tokens", 0))

    except Exception as err:
        print(f"❌ [Part B 실패]: {err}")

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part C] 추론 OFF + 필터링 동시 적용 (100% Pure Strict JSON 보장, no_think_max_tokens=512)
    # -------------------------------------------------------------------------
    print("▶️ [Part C] 추론 OFF + 필터링 동시 적용 (NO_THINK_SYSTEM_PROMPT 적용 - Pure JSON)...")
    payload_c = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": f"{NO_THINK_SYSTEM_PROMPT}\nJSON Schema:\n{schema_str}"},
            {"role": "user", "content": comment}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": config["no_think_max_tokens"]
    }

    t_start_c = time.time()
    try:
        with get_httpx_client() as client:
            resp_c = client.post(TARGET_URL, json=payload_c, headers={"Connection": "close"})
            resp_c.raise_for_status()
            t_end_c = time.time()
            res_c = resp_c.json()
            raw_c = res_c["choices"][0]["message"]["content"] or ""
            clean_c = clean_think_tags(raw_c, show_think=False)

            parsed_c = StockSentiment.model_validate_json(clean_c)
            print(f"✅ [Part C Pure JSON Pydantic 검증 성공]:")
            print(f"   - 화자: {parsed_c.speaker} | 종목: {parsed_c.stock_name} | 감성: {parsed_c.sentiment}")
            m_c = print_performance_summary("Part C: 추론 OFF + Pure JSON", t_start_c, t_end_c, gen_tokens=res_c.get("usage", {}).get("completion_tokens", 0))

    except Exception as err:
        print(f"❌ [Part C 실패]: {err}")


if __name__ == "__main__":
    main()
