"""openai_11_structured_batch.py
================================================================================
[11단계 실습] OpenAI SDK 기반 Pydantic v2 배치(Batch) 멀티 댓글 일괄 구조화 출력 (Part A/B/C)
================================================================================
학습 목표:
1. OpenAI SDK로 비정형 댓글 리스트 묶음을 1회 API 호출로 일괄 전달하여 배치 분석을 수행합니다.
2. 10번 실습의 3단계 구조화 설정(Part A/B benchmark_max_tokens=2048 / Part C default_max_tokens=1024)을 배치 모델에 확장 적용하여 수집 데이터 절단을 완전히 방지합니다.

실행 명령어:
    uv run python openai_11_structured_batch.py
"""

import time
import json
from typing import List
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


class StockComment(BaseModel):
    speaker: str = Field(description="작성자 닉네임")
    target: str = Field(description="정식 종목명 (삼성전자, 현대차, 네이버 등)")
    sentiment: str = Field(description="긍정, 부정, 중립 중 하나")


class BatchAnalysis(BaseModel):
    results: List[StockComment]


def main():
    print_section_header("11. OpenAI SDK Pydantic v2 배치 멀티 데이터 구조화 출력 3단계(Part A / B / C) 비교 실습")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    client = get_openai_client()

    schema_str = json.dumps(BatchAnalysis.model_json_schema(), ensure_ascii=False, indent=2)
    comments = [
        "개미왕: 삼전 급등해서 풀매수 쳤습니다.",
        "차트신: 현대차 20일선 돌파 모습이 긍정적입니다.",
        "네이버보이: 네이버 목표가 하향 나와서 풀매도 했습니다."
    ]
    user_payload = "\n".join([f"- {c}" for c in comments])

    # -------------------------------------------------------------------------
    # [Part A] SDK 배치 일반 구조화 요청 (benchmark_max_tokens=2048)
    # -------------------------------------------------------------------------
    print(f"▶️ [Part A] SDK 배치 일반 구조화 요청 전송 (max_tokens={config['benchmark_max_tokens']})...")
    t_start_a = time.time()
    try:
        comp_a = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": f"다음 JSON Schema 규격을 반드시 준수하세요:\n{schema_str}"},
                {"role": "user", "content": f"다음 댓글들을 일괄 분석하여 results 배열로 반환하세요:\n{user_payload}"}
            ],
            response_format={"type": "json_object"},
            max_tokens=config["benchmark_max_tokens"],
            timeout=180.0
        )
        t_end_a = time.time()
        raw_a = comp_a.choices[0].message.content or ""

        print(f"💬 [Part A SDK 원본 응답 요약]: {raw_a[:100]}...")
        m_a = print_performance_summary("Part A: SDK 배치 일반 구조화", t_start_a, t_end_a, gen_tokens=comp_a.usage.completion_tokens if comp_a.usage else 0)

    except Exception as err:
        print(f"❌ [Part A SDK 실패]: {err}")

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part B] SDK 배치 추론 필터링 적용 (benchmark_max_tokens=2048)
    # -------------------------------------------------------------------------
    print(f"▶️ [Part B] SDK 배치 추론 필터링 적용 요청 전송 (생각 태그 세척 후 Pydantic 검증, max_tokens={config['benchmark_max_tokens']})...")
    t_start_b = time.time()
    try:
        comp_b = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": f"다음 JSON Schema 규격을 반드시 준수하세요:\n{schema_str}"},
                {"role": "user", "content": f"다음 댓글들을 일괄 분석하여 results 배열로 반환하세요:\n{user_payload}"}
            ],
            response_format={"type": "json_object"},
            max_tokens=config["benchmark_max_tokens"],
            timeout=180.0
        )
        t_end_b = time.time()
        raw_b = comp_b.choices[0].message.content or ""
        clean_b = clean_think_tags(raw_b, show_think=False)

        parsed_b = BatchAnalysis.model_validate_json(clean_b)
        print(f"✅ [Part B SDK Pydantic 검증 파싱 성공]: {len(parsed_b.results)}개 항목 수신")
        m_b = print_performance_summary("Part B: SDK 배치 추론 필터링", t_start_b, t_end_b, gen_tokens=comp_b.usage.completion_tokens if comp_b.usage else 0)

    except Exception as err:
        print(f"❌ [Part B SDK 실패]: {err}")

    print("-" * 65)

    # -------------------------------------------------------------------------
    # [Part C] SDK 배치 추론 OFF + 필터링 동시 적용 (100% Pure Strict JSON, default_max_tokens=1024)
    # -------------------------------------------------------------------------
    print(f"▶️ [Part C] SDK 배치 추론 OFF + 필터링 동시 적용 (NO_THINK_SYSTEM_PROMPT 적용, max_tokens={config['default_max_tokens']})...")
    t_start_c = time.time()
    try:
        comp_c = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": f"{NO_THINK_SYSTEM_PROMPT}\nJSON Schema:\n{schema_str}"},
                {"role": "user", "content": f"다음 댓글들을 일괄 분석하여 results 배열로 반환하세요:\n{user_payload}"}
            ],
            response_format={"type": "json_object"},
            max_tokens=config["default_max_tokens"],
            timeout=180.0
        )
        t_end_c = time.time()
        raw_c = comp_c.choices[0].message.content or ""
        clean_c = clean_think_tags(raw_c, show_think=False)

        parsed_c = BatchAnalysis.model_validate_json(clean_c)
        print(f"✅ [Part C SDK 배치 Pydantic 검증 파싱 성공]: {len(parsed_c.results)}개 항목 추출")
        for idx, item in enumerate(parsed_c.results, 1):
            print(f"  [{idx}] 작성자: {item.speaker:<8} | 종목: {item.target:<6} | 감성: {item.sentiment}")

        m_c = print_performance_summary("Part C: SDK 배치 추론 OFF + Pure JSON", t_start_c, t_end_c, gen_tokens=comp_c.usage.completion_tokens if comp_c.usage else 0)

    except Exception as err:
        print(f"❌ [Part C SDK 실패]: {err}")


if __name__ == "__main__":
    main()
