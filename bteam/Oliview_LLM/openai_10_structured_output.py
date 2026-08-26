"""openai_10_structured_output.py
================================================================================
[10단계 실습] OpenAI SDK 기반 Pydantic v2 단일 구조화 출력 3단계 제어 비교 (Part A / B / C)
================================================================================
학습 목표:
1. OpenAI SDK client.chat.completions.create(response_format={"type": "json_object"}) 규격을 배웁니다.
2. 3단계 구조화 출력을 비교합니다:
   - Part A: 일반 구조화 요청 (Strict JSON 포맷 유도, benchmark_max_tokens=2048)
   - Part B: 수신 응답 내 추론 태그 세척 (Reasoning Filtered, benchmark_max_tokens=2048)
   - Part C: 추론 OFF (NO_THINK_SYSTEM_PROMPT) + 세척으로 100% Pure JSON만 보장 (no_think_max_tokens=512)

실행 명령어:
    uv run python openai_10_structured_output.py
"""

import time
import json
from pydantic import BaseModel, Field
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


class StockSentiment(BaseModel):
    speaker: str = Field(description="작성자 닉네임")
    stock_name: str = Field(description="정식 종목명 (예: 삼성전자)")
    sentiment: str = Field(description="긍정, 부정, 중립 중 하나")


def main():
    print_section_header("10. OpenAI SDK Pydantic v2 단일 구조화 출력 3단계(Part A / B / C) 비교 실습")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    client = get_openai_client()

    schema_str = json.dumps(StockSentiment.model_json_schema(), ensure_ascii=False, indent=2)
    comment = "개미왕: 삼전 시외 급등하길래 바로 풀매수 쳤습니다."

    # -------------------------------------------------------------------------
    # [Part A] SDK 일반 구조화 요청 (생각 태그 미정제 원본 수신, benchmark_max_tokens=2048)
    # -------------------------------------------------------------------------
    print("▶️ [Part A] SDK 일반 구조화 요청 전송 (생각 과정 미정제 원본 수신)...")
    t_start_a = time.time()
    try:
        comp_a = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": f"다음 JSON Schema 규격을 반드시 준수하세요:\n{schema_str}"},
                {"role": "user", "content": comment}
            ],
            response_format={"type": "json_object"},
            max_tokens=config["benchmark_max_tokens"]
        )
        t_end_a = time.time()
        raw_a = comp_a.choices[0].message.content or ""

        print(f"💬 [Part A SDK 원본 응답]:\n{raw_a}")
        m_a = print_performance_summary("Part A: SDK 일반 구조화 요청", t_start_a, t_end_a, gen_tokens=comp_a.usage.completion_tokens if comp_a.usage else 0)

    except Exception as err:
        print(f"❌ [Part A SDK 실패]: {err}")

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part B] SDK 추론 필터링 적용 (생각 태그 세척 후 Pydantic 파싱, benchmark_max_tokens=2048)
    # -------------------------------------------------------------------------
    print("▶️ [Part B] SDK 추론 필터링 적용 요청 전송 (생각 태그 세척 후 Pydantic 검증)...")
    t_start_b = time.time()
    try:
        comp_b = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": f"다음 JSON Schema 규격을 반드시 준수하세요:\n{schema_str}"},
                {"role": "user", "content": comment}
            ],
            response_format={"type": "json_object"},
            max_tokens=config["benchmark_max_tokens"]
        )
        t_end_b = time.time()
        raw_b = comp_b.choices[0].message.content or ""
        clean_b = clean_think_tags(raw_b, show_think=False)

        parsed_b = StockSentiment.model_validate_json(clean_b)
        print(f"✅ [Part B SDK Pydantic 검증 객체]: {parsed_b}")
        m_b = print_performance_summary("Part B: SDK 추론 필터링 적용", t_start_b, t_end_b, gen_tokens=comp_b.usage.completion_tokens if comp_b.usage else 0)

    except Exception as err:
        print(f"❌ [Part B SDK 실패]: {err}")

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part C] SDK 추론 OFF + 필터링 동시 적용 (100% Pure Strict JSON 보장, no_think_max_tokens=512)
    # -------------------------------------------------------------------------
    print("▶️ [Part C] SDK 추론 OFF + 필터링 동시 적용 (NO_THINK_SYSTEM_PROMPT 적용 - Pure JSON)...")
    t_start_c = time.time()
    try:
        comp_c = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": f"{NO_THINK_SYSTEM_PROMPT}\nJSON Schema:\n{schema_str}"},
                {"role": "user", "content": comment}
            ],
            response_format={"type": "json_object"},
            max_tokens=config["no_think_max_tokens"]
        )
        t_end_c = time.time()
        raw_c = comp_c.choices[0].message.content or ""
        clean_c = clean_think_tags(raw_c, show_think=False)

        parsed_c = StockSentiment.model_validate_json(clean_c)
        print(f"✅ [Part C SDK Pure JSON Pydantic 검증 성공]:")
        print(f"   - 화자: {parsed_c.speaker} | 종목: {parsed_c.stock_name} | 감성: {parsed_c.sentiment}")
        m_c = print_performance_summary("Part C: SDK 추론 OFF + Pure JSON", t_start_c, t_end_c, gen_tokens=comp_c.usage.completion_tokens if comp_c.usage else 0)

    except Exception as err:
        print(f"❌ [Part C SDK 실패]: {err}")


if __name__ == "__main__":
    main()
