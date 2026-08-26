"""openai_08_embedding.py
================================================================================
[8단계 실습] OpenAI SDK 기반 BGE M3 수치 벡터(Embedding) 변환 (8090 포트)
================================================================================
학습 목표:
1. OpenAI SDK client.embeddings.create(input=[...]) 표준 메서드를 사용합니다.
2. 텍스트 데이터를 1024차원 수치 좌표(벡터)로 치환하여 벡터 검색(RAG)의 기본을 익힙니다.

실행 명령어:
    uv run python openai_08_embedding.py
"""

import time
from common import (
    check_server_health,
    load_sample_config,
    print_section_header,
    print_performance_summary,
    get_openai_client
)

config = load_sample_config()
SERVER_HOST = config["server_host"]
EMBEDDING_PORT = config.get("embedding_port", 8090)  # 임베딩 전용 8090 포트
MODEL_NAME = config.get("embedding_model", "bge-m3")


def main():
    print_section_header("08. OpenAI SDK 규격 BGE M3 1024차원 수치 벡터 변환 실습 (8090 포트)")

    if not check_server_health(SERVER_HOST, EMBEDDING_PORT, "BGE M3 임베딩 서빙"):
        return

    # 독립 임베딩 포트(8090) 주소가 설정된 OpenAI 클라이언트 생성
    client = get_openai_client(port=EMBEDDING_PORT)

    batch_texts = [
        "vllm_serv는 고성능 LLM 및 임베딩 동시 서빙 플랫폼입니다.",
        "파이썬 기반 AI 서비스 개발자 양성과정 실습 수트입니다."
    ]

    t_start = time.time()
    # SDK의 embeddings.create 메서드로 배치 수치 벡터 변환 수행
    resp = client.embeddings.create(model=MODEL_NAME, input=batch_texts)
    t_end = time.time()

    gen_tokens = resp.usage.prompt_tokens if resp.usage else 0

    print(f"✅ [SDK 임베딩 변환 성공]: 배치 문장 수 {len(resp.data)}개")
    for idx, item in enumerate(resp.data):
        vec = item.embedding
        print(f"  [{idx+1}] 차원: {len(vec)}차원 | 상위 5개 값: {vec[:5]}")

    print_performance_summary("SDK 임베딩", t_start, t_end, gen_tokens=gen_tokens)


if __name__ == "__main__":
    main()
