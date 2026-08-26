import os
import gc
import torch
from rank_bm25 import BM25Okapi
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from .utils import get_bge_m3_device
from .keyword_extractor import tokenize_kiwi

_bge_m3_embeddings_instance = None

def get_bge_m3_embeddings() -> HuggingFaceEmbeddings:
    """
    BAAI/bge-m3 임베딩 모델 인스턴스를 싱글톤으로 로드/재사용하여 매 호출 시 가중치 재로딩을 방지합니다.
    """
    global _bge_m3_embeddings_instance
    if _bge_m3_embeddings_instance is None:
        device = get_bge_m3_device()
        _bge_m3_embeddings_instance = HuggingFaceEmbeddings(
            model_name="BAAI/bge-m3",
            model_kwargs={"device": device}
        )
    return _bge_m3_embeddings_instance


class BM25Search:
    """
    Kiwi 형태소 토크나이저와 rank-bm25 패키지를 래핑하여 키워드 매칭 검색 서비스를 제공하는 클래스.
    """
    def __init__(self, corpus: list[str]):
        self.corpus = corpus
        self.tokenized_corpus = [tokenize_kiwi(doc) for doc in corpus]
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)
        else:
            self.bm25 = None

    def search(self, query: str, k: int = 3) -> list[tuple[str, float]]:
        """
        쿼리를 입력받아 코퍼스 내 문서들과의 BM25 스코어를 연산하고 정렬해 상위 k개를 반환합니다.
        반환 형태: [(Document_Text, Score), ...]
        """
        if not query or not self.corpus or self.bm25 is None:
            return []
            
        tokenized_query = tokenize_kiwi(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        results = []
        for idx, doc in enumerate(self.corpus):
            results.append((doc, float(scores[idx])))
            
        results_sorted = sorted(results, key=lambda x: x[1], reverse=True)
        return results_sorted[:k]


def search_documents(query: str, db_path: str = "chroma_db_test", k: int = 3) -> tuple[list, Chroma]:
    """
    로컬 Chroma DB를 로드하여 입력 쿼리와의 코사인 유사도 기반 similarity_search_with_score를 수행합니다.
    검색 결과 문서 목록(점수 포함)과 Chroma 인스턴스 튜플을 반환합니다.
    """
    if not os.path.exists(db_path):
        return [], None
        
    try:
        embeddings = get_bge_m3_embeddings()
        
        vector_store = Chroma(
            persist_directory=db_path,
            embedding_function=embeddings,
            collection_metadata={"hnsw:space": "cosine"}
        )
        
        results = vector_store.similarity_search_with_score(query, k=k)
        return results, vector_store
    except Exception as e:
        print(f"Chroma DB 검색 중 에러 발생: {e}")
        return [], None


def reciprocal_rank_fusion(
    bm25_rankings: list[str],
    vector_rankings: list[str],
    k: int = 60
) -> list[tuple[str, float]]:
    """
    BM25 순위 리스트와 Vector 순위 리스트를 RRF 알고리즘으로 상호 재정렬(Reciprocal Rank Fusion)합니다.
    """
    rrf_scores = {}

    for rank, doc in enumerate(bm25_rankings, 1):
        if doc not in rrf_scores:
            rrf_scores[doc] = 0.0
        rrf_scores[doc] += 1.0 / (k + rank)

    for rank, doc in enumerate(vector_rankings, 1):
        if doc not in rrf_scores:
            rrf_scores[doc] = 0.0
        rrf_scores[doc] += 1.0 / (k + rank)

    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results
