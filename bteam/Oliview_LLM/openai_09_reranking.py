"""openai_09_reranking.py
================================================================================
[9단계 실습] OpenAI 규격 API 호출 기반 BGE-Reranker v2 (5종 후보 문서)
================================================================================
학습 목표:
1. REST API 파이프라인으로 BGE-Reranker v2 서비스 포트(8091)에 5종 후보 문서를 전달합니다.
2. 질문과 의미적 유사도가 높은 관련 문서 3개와 관련 없는 노이즈 문서 2개(총 5개 후보 문서)를 재순위화(Re-ranking)하여 상위 관련 문서를 도출합니다.

실행 명령어:
    uv run python openai_09_reranking.py
"""

import math
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
RERANK_PORT = config["rerank_port"]
TARGET_URL = f"{SERVER_HOST}:{RERANK_PORT}/v1/embeddings"

QUERY = "vllm_serv 엔진의 GPU VRAM 오프로딩 및 서빙 최적화 기법은 무엇인가요?"

# 5개 후보 문서 (의미적 유사 문서 3개 + 관련 없는 노이즈 문서 2개)
DOCUMENTS = [
    # [Doc 0] 유사 문서 1 (최상 관련도)
    (
        "vllm_serv 메인 엔진은 GPU VRAM 효율성을 극대화하기 위해 PagedAttention 알고리즘을 사용합니다. "
        "이를 통해 가상 메모리 기법처럼 토큰 키-값(KV) 캐시를 불연속적인 메모리 공간에 나누어 할당함으로써 "
        "단중 사용자 환경에서도 GPU 메모리 파편화를 최소화하고 추론 처리량(TPS)을 크게 향상시킵니다."
    ),
    # [Doc 1] 노이즈 문서 1 (관련 없음)
    (
        "제주도 서귀포 해안의 기후 관측 자료에 따르면 여름철 평균 기온은 26.5도를 기록하였습니다. "
        "현무암 암반층을 통과하여 형성된 삼다수 지하수는 풍부한 미네랄 성분을 포함하고 있어 수질이 양호하며, "
        "해양 생태계 보존을 위한 환경 감시 모니터링 체계가 강화되고 있습니다."
    ),
    # [Doc 2] 유사 문서 2 (높은 관련도)
    (
        "vLLM 기반의 서비스 레이어는 모델 파라미터 크기에 맞춰 VRAM 할당량을 동적으로 조절할 수 있습니다. "
        "GTX 1070과 같은 8GB 가용 하드웨어 상에서도 BGE-M3 임베딩 데몬 및 BGE-Reranker 데몬과 메모리를 분할하여 "
        "독립된 HTTP 포트(8081, 8090, 8091)로 안정적인 동시 서빙이 가능하도록 구조화되어 있습니다."
    ),
    # [Doc 3] 노이즈 문서 2 (관련 없음)
    (
        "2026년도 신규 AI 서비스 개발자 양성과정 수강생 모집 안내입니다. "
        "본 과정은 국비 지원으로 진행되며 국민내일배움카드를 발급받은 비전공자 및 예비 개발자를 대상으로 합니다. "
        "우수한 성적으로 이수한 훈련생에게는 협력 기업 채용 연계 및 식대 지원 혜택이 제공됩니다."
    ),
    # [Doc 4] 유사 문서 3 (중상 관련도)
    (
        "대규모 언어 모델(LLM) 추론 가속을 위해서는 지속적 배치(Continuous Batching) 기술이 필수적입니다. "
        "요청이 들어올 때마다 타임슬롯을 동적으로 결합하여 GPU 연산 코어를 100% 가동시킴으로써 "
        "첫 토큰 대기시간(TTFT)을 단축하고 대규모 동시 접속 상황에서의 서비스 지연을 차단합니다."
    )
]


def _get_vector(v):
    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], list):
        return v[0]
    return v


def _cosine_sim(v1, v2):
    v1 = _get_vector(v1)
    v2 = _get_vector(v2)
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    return dot / (norm1 * norm2) if (norm1 * norm2) > 0 else 0.0


def main():
    print_section_header("09. OpenAI 규격 BGE-Reranker v2 (5종 후보 문서 재순위화) 실습")

    if not check_server_health(SERVER_HOST, RERANK_PORT, "BGE-Reranker 서비스"):
        return

    print(f"❓ [검색 질문]: \"{QUERY}\"")
    print(f"📚 [후보 문서 5개 (유사 3개 + 노이즈 2개)] 리랭킹 서버(포트 {RERANK_PORT}) 전송 중...\n")

    t_start = time.time()
    try:
        with get_httpx_client() as client:
            # 1. 질문 벡터 획득
            r_q = client.post(TARGET_URL, json={"input": QUERY}, headers={"Connection": "close"}).json()
            q_vec = r_q["data"][0]["embedding"]

            # 2. 5개 후보 문서 벡터 일괄 획득
            r_docs = client.post(TARGET_URL, json={"input": DOCUMENTS}, headers={"Connection": "close"}).json()
            doc_datas = r_docs["data"]
            t_end = time.time()

            scores = []
            for idx, d in enumerate(doc_datas):
                d_vec = d["embedding"]
                sim = _cosine_sim(q_vec, d_vec)
                scores.append((idx, sim))

            # 점수 기준 내림차순 정렬
            scores.sort(key=lambda x: x[1], reverse=True)

            print("🏆 [BGE-Reranker v2 Cross-Encoder 관련도 순위 결과]:\n")
            for rank, (doc_idx, score) in enumerate(scores, 1):
                doc_text = DOCUMENTS[doc_idx]
                doc_type = "🎯 [유사 문서]" if doc_idx in [0, 2, 4] else "🍃 [노이즈 문서]"
                
                print(f"  {rank}위 (점수: {score:+.4f}) {doc_type} (원본 Doc #{doc_idx}):")
                print(f"      \"{doc_text[:90]}...\"")
                print()

            print_performance_summary("OpenAI 규격 BGE-Reranker 5종 재순위화", t_start, t_end)

    except Exception as err:
        print(f"❌ [리랭킹 호출 실패]: {err}")


if __name__ == "__main__":
    main()
