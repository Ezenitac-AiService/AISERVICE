import gc
import torch
from sentence_transformers import CrossEncoder

from .utils import get_bge_m3_device

_bge_reranker_instance = None

def get_bge_reranker_model() -> CrossEncoder:
    """
    BAAI/bge-reranker-v2-m3 모델 인스턴스를 싱글톤으로 로드/재사용하여 매 호출 시 가중치 재로딩을 방지합니다.
    """
    global _bge_reranker_instance
    if _bge_reranker_instance is None:
        device = get_bge_m3_device()
        _bge_reranker_instance = CrossEncoder(
            "BAAI/bge-reranker-v2-m3",
            max_length=512,
            device=device
        )
    return _bge_reranker_instance


def rerank_documents(query: str, docs: list[dict], k: int = 3) -> list[dict]:
    """
    BAAI/bge-reranker-v2-m3 오픈소스 리랭커 모델을 활용하여 하이브리드 결과를 재정렬합니다.
    각 문서의 dict 구조 내에 'score' 키로 최종 점수를 매핑하여 정렬 후 상위 k개를 반환합니다.
    """
    if not query or not docs:
        return []
        
    try:
        model = get_bge_reranker_model()
        
        pairs = [[query, doc.get("page_content", "")] for doc in docs]
        scores = model.predict(pairs)
        
        for idx, doc in enumerate(docs):
            doc["score"] = float(scores[idx])
            
        reranked_docs = sorted(docs, key=lambda x: x["score"], reverse=True)
        return reranked_docs[:k]
    except Exception as e:
        print(f"리랭킹 연산 실패: {e}")
        return docs[:k]
