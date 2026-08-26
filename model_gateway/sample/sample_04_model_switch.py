"""sample_04_model_switch.py
================================================================================
[4단계 실습] httpx 기반 동적 모델 교체(Model Switching) 가용 모델 전체 실측
================================================================================
학습 목표:
1. REST API 호출 시 payload의 "model" 인자를 바꿔가며 현재 연결된 서버(RTX 3060 / GTX 1070)에 실제 로드된 LLM 대화 모델을 동적 조회(get_available_llm_models)하여 라이브 전송합니다.
2. 각 모델별 내면 고찰 방식(show_think=True)과 완결 답변이 절단되지 않도록 config.json의 benchmark_max_tokens(2048 토큰 = 2K)를 동적으로 로드하여 전수 벤치마크를 수행합니다.

실행 명령어:
    uv run python sample_04_model_switch.py
"""

import time
from common import (
    check_server_health,
    load_sample_config,
    print_section_header,
    print_performance_summary,
    get_httpx_client,
    clean_think_tags,
    get_available_llm_models
)

config = load_sample_config()
SERVER_HOST = config["server_host"]
MAIN_PORT = config["main_port"]
TARGET_URL = f"{SERVER_HOST}:{MAIN_PORT}/v1/chat/completions"
BENCHMARKS = config.get("model_benchmarks", {})
TARGET_MODELS = get_available_llm_models()  # 서버에 실제 로드된 가용 LLM 모델 실시간 동적 탐색
PROMPT = config.get("sample_prompt", "인공지능의 정의를 1문장으로 작성해 주세요.")
SYSTEM_PROMPT = config.get("sample_system_prompt", "당신은 IT 및 AI 기술 전문 어시스턴트입니다.")
TIMEOUT_SEC = config.get("request_timeout_seconds", 180.0)


def main():
    print_section_header("04. httpx 동적 모델 변경(Model Switching) 가용 모델 전체 실측 벤치마크")

    if not check_server_health(SERVER_HOST, MAIN_PORT, "vllm_serv 메인 API"):
        return

    print(f"📡 [현재 활성 서버]: {SERVER_HOST}:{MAIN_PORT}")
    print(f"📝 동일 질문으로 서버 실시간 가용 LLM 모델 {len(TARGET_MODELS)}종 {TARGET_MODELS} 라이브 호출 시작 (max_tokens={config['benchmark_max_tokens']})...\n")

    for m_id in TARGET_MODELS:
        b_info = BENCHMARKS.get(m_id, {})
        vram_mb = b_info.get("peak_vram_mb", 0)
        rec_ctx = b_info.get("recommended_context_length", 4096)
        max_ctx = b_info.get("max_context_length", 8192)
        bench_tps = b_info.get("tpot_tok_per_sec", 0.0)

        print(f"📡 [모델 전송] '{m_id}' (피크 VRAM: {vram_mb}MB, 추천맥락: {rec_ctx}/최대 {max_ctx}, 스펙 TPS: {bench_tps})")

        payload = {
            "model": m_id,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": PROMPT}
            ],
            "max_tokens": config["benchmark_max_tokens"]  # 2K 벤치마크 한도 동적 로드
        }

        t_start = time.time()
        try:
            with get_httpx_client(timeout=TIMEOUT_SEC) as client:
                resp = client.post(TARGET_URL, json=payload, headers={"Connection": "close"})
                resp.raise_for_status()
                t_end = time.time()

                res = resp.json()
                responded_model = res.get("model")
                raw_answer = res["choices"][0]["message"]["content"] or ""
                # 모델별 사고 방식 비교를 위해 show_think=True 적용
                clean_answer = clean_think_tags(raw_answer, show_think=True)
                gen_tokens = res.get("usage", {}).get("completion_tokens", 0)

                print(f"\n{clean_answer}")
                summary = print_performance_summary(
                    f"httpx 모델 [{m_id}]",
                    t_start,
                    t_end,
                    gen_tokens=gen_tokens,
                    requested_model=m_id,
                    responded_model=responded_model
                )
                if not summary.get("is_model_matched"):
                    print(f"❌ [모델 불일치 경고] 요청 모델({m_id})과 서버 응답 모델({responded_model})이 다릅니다.")
                print("-" * 65)

        except Exception as err:
            print(f"❌ [{m_id} 호출 실패]: {err}\n")


if __name__ == "__main__":
    main()

