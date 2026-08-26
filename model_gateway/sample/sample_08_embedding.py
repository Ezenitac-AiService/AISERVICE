"""sample_08_embedding.py
================================================================================
[8단계 실습] httpx 기반 BGE M3 수치 벡터(Embedding) 변환 (8090 포트)
================================================================================
학습 목표:
1. 텍스트 문장을 인공지능이 계산 가능한 1024차원의 실수 벡터(Vector)로 변환하는 법을 배웁니다.
2. 독립된 임베딩 서빙 포트(8090)로 /v1/embeddings 엔드포인트를 호출하는 법을 습득합니다.

실행 명령어:
    uv run python sample_08_embedding.py
"""

import time
from common import (
    check_server_health,
    load_sample_config,
    print_section_header,
    print_performance_summary,
    get_httpx_client
)

config = load_sample_config()
SERVER_HOST = config["server_host"]
EMBEDDING_PORT = config.get("embedding_port", 8090)  # 임베딩 전용 8090 포트
MODEL_NAME = config.get("embedding_model", "bge-m3")   # 1024차원 bge-m3 모델
TARGET_URL = f"{SERVER_HOST}:{EMBEDDING_PORT}/v1/embeddings"


def main():
    print_section_header("08. httpx 규격 BGE M3 1024차원 수치 벡터 변환 실습 (8090 포트)")

    # 1. 독립된 임베딩 서빙 포트(8090)가 준비되어 있는지 사전 검사합니다.
    if not check_server_health(SERVER_HOST, EMBEDDING_PORT, "BGE M3 임베딩 서빙"):
        return

    # 2. 벡터로 변환하고자 하는 텍스트 리스트 (단일 또는 배치 묶음)
    batch_texts = [
        "vllm_serv는 고성능 LLM 및 임베딩 동시 서빙 플랫폼입니다.",
        "파이썬 기반 AI 서비스 개발자 양성과정 실습 수트입니다."
    ]

    payload = {"model": MODEL_NAME, "input": batch_texts}

    t_start = time.time()
    with get_httpx_client() as client:
        resp = client.post(TARGET_URL, json=payload, headers={"Connection": "close"})
        resp.raise_for_status()
        t_end = time.time()

        res = resp.json()
        items = res.get("data", [])
        gen_tokens = res.get("usage", {}).get("prompt_tokens", 0)

        # 3. 추출된 1024차원 임베딩 수치 벡터의 상위 5개 수치를 확인합니다.
        print(f"✅ [임베딩 변환 성공]: 배치 문장 수 {len(items)}개")
        for idx, item in enumerate(items):
            vec = item["embedding"]
            print(f"  [{idx+1}] 차원: {len(vec)}차원 | 상위 5개 값: {vec[:5]}")

        print_performance_summary("httpx 임베딩", t_start, t_end, gen_tokens=gen_tokens)


if __name__ == "__main__":
    main()
