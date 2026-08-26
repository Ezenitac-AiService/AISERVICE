"""
RAG Agent Workflow States & Nodes Module
"""

import os
import sys
import json
from typing import TypedDict, NotRequired, List, Dict, Any
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from evaluator.utils import get_bge_m3_device, safe_remove_directory
from evaluator.prompts import (
    RAG_SYSTEM_PROMPT,
    get_rag_prompt,
    DECOMPOSE_SYSTEM_PROMPT,
    SYNTHESIZE_SYSTEM_PROMPT,
)
from evaluator.hybrid_retriever import (
    BM25Search,
    search_documents,
    reciprocal_rank_fusion,
    get_bge_m3_embeddings,
)
from evaluator.reranker import rerank_documents, get_bge_reranker_model

load_dotenv()

def get_project_root() -> str:
    current = os.path.abspath(os.path.dirname(__file__))
    if os.path.exists(os.path.join(current, "pyproject.toml")) or os.path.exists(os.path.join(current, "data")):
        return current
    parent = os.path.abspath(os.path.join(current, ".."))
    if os.path.exists(os.path.join(parent, "pyproject.toml")) or os.path.exists(os.path.join(parent, "data")):
        return parent
    return current


class RAGState(TypedDict):
    """
    LangGraph 에이전트 RAG 워크플로우 전역 공유 상태 스키마.
    """
    question: str
    keywords: list[str]
    documents: list[dict]
    generation: str
    loop_count: int
    relevance: NotRequired[str]


class MultiTargetState(TypedDict):
    """
    다중 대상 분할 검색 및 통합 RAG 전역 상태 스키마.
    """
    question: str
    sub_queries: list[str]
    sub_documents: dict[str, list[dict]]
    generation: str


def ensure_corpus_db(db_path: str = "chroma_db_test", min_chunks: int = 15) -> str:
    """
    DB 경로가 존재하지 않거나 전체 11개 코퍼스 청크 수(min_chunks)보다 적은 경우 data/ 전체 샘플로부터 재구축
    """
    base_dir = get_project_root()
    if not os.path.isabs(db_path):
        resolved_db_path = os.path.join(base_dir, db_path)
    else:
        resolved_db_path = db_path

    need_build = False
    if not os.path.exists(resolved_db_path):
        need_build = True
    else:
        try:
            from langchain_chroma import Chroma
            embeddings = get_bge_m3_embeddings()
            vector_store = Chroma(
                persist_directory=resolved_db_path,
                embedding_function=embeddings,
                collection_metadata={"hnsw:space": "cosine"}
            )
            doc_count = len(vector_store.get().get("documents", []))
            if doc_count < min_chunks:
                need_build = True
        except Exception:
            need_build = True

    if need_build:
        data_dir = os.path.join(base_dir, "data")
        if os.path.exists(data_dir):
            try:
                from evaluator.document_loader import load_and_chunk_documents
                from langchain_chroma import Chroma

                print(f"[INFO] 전체 코퍼스 DB (11개 문서) 인덱싱 진행: {resolved_db_path}")
                chunks = load_and_chunk_documents(data_dir)
                if chunks:
                    if os.path.exists(resolved_db_path):
                        safe_remove_directory(resolved_db_path)
                    embeddings = get_bge_m3_embeddings()
                    texts = [chunk.text_content for chunk in chunks]
                    metadatas = []
                    for chunk in chunks:
                        meta = dict(chunk.metadata)
                        if "keywords" in meta and isinstance(meta["keywords"], list):
                            meta["keywords"] = ", ".join(meta["keywords"])
                        meta["chunk_id"] = chunk.chunk_id
                        metadatas.append(meta)

                    Chroma.from_texts(
                        texts=texts,
                        embedding=embeddings,
                        persist_directory=resolved_db_path,
                        metadatas=metadatas,
                        collection_metadata={"hnsw:space": "cosine"}
                    )
                    print(f"[INFO] 전체 코퍼스 DB 구축 완료 ({len(texts)}개 청크 적재됨)")
            except Exception as e:
                print(f"[WARNING] DB 구축 실패: {e}")

    return resolved_db_path


def hybrid_ensemble_search_node(
    query: str,
    db_path: str = "chroma_db_test",
    k: int = 10,
    k_rrf: int = 60
) -> list[dict]:
    resolved_path = ensure_corpus_db(db_path)
    if not os.path.exists(resolved_path):
        return []

    vector_results, vector_store = search_documents(query, db_path=resolved_path, k=k)
    if not vector_store:
        return []

    all_docs = vector_store.get()
    corpus = all_docs.get("documents", [])
    metadatas = all_docs.get("metadatas", [])

    if not corpus:
        return []

    bm25_engine = BM25Search(corpus)
    bm25_scores = bm25_engine.search(query, k=k)

    bm25_rank_list = [doc for doc, score in bm25_scores]
    vector_rank_list = [doc.page_content for doc, score in vector_results]

    fusion_results = reciprocal_rank_fusion(bm25_rank_list, vector_rank_list, k=k_rrf)

    meta_map = {}
    for doc_text, meta in zip(corpus, metadatas):
        meta_map[doc_text] = meta

    final_docs = []
    for doc_text, rrf_score in fusion_results[:k]:
        final_docs.append({
            "page_content": doc_text,
            "metadata": meta_map.get(doc_text, {}),
            "score": rrf_score
        })

    return final_docs


def retrieve(state: RAGState, db_path: str = "chroma_db_test") -> dict:
    """
    Retrieve 노드: 질문에 대한 하이브리드 검색 및 CrossEncoder 리랭킹을 수행합니다.
    """
    question = state["question"]
    initial_docs = hybrid_ensemble_search_node(question, db_path=db_path, k=10, k_rrf=60)
    reranked_docs = rerank_documents(question, initial_docs, k=6)
    return {"documents": reranked_docs}


def generate(state: RAGState, mock_response: str = None) -> dict:
    """
    Generate 노드: 질문과 참조 문서들을 바탕으로 답변을 작성합니다.
    """
    if mock_response:
        return {"generation": mock_response}

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"generation": "[ERROR] GROQ_API_KEY가 설정되지 않았거나 API 호출 중 오류가 발생했습니다."}

    question = state["question"]
    documents = state.get("documents", [])

    context_list = [doc.get("page_content", "") for doc in documents]
    context = "\n\n".join(context_list)

    try:
        llm = ChatGroq(
            model=os.getenv("CURRENT_GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=0,
            max_tokens=1024,
            api_key=api_key,
        )
        prompt = get_rag_prompt()
        chain = prompt | llm
        response = chain.invoke({"context": context, "question": question})
        return {"generation": str(response.content)}
    except Exception as e:
        return {"generation": f"[ERROR] GROQ_API_KEY가 설정되지 않았거나 API 호출 중 오류가 발생했습니다: {e}"}


def decompose_query(state: MultiTargetState, mock_response: str = None) -> dict:
    """
    1. 질의 분해 노드: 복합 질문을 감지하여 대상별 서브 쿼리 리스트로 분할합니다.
    """
    if mock_response:
        try:
            sub_queries = json.loads(mock_response)
            return {"sub_queries": sub_queries}
        except Exception:
            return {"sub_queries": [state["question"]]}

    question = state["question"]
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"sub_queries": [question]}

    try:
        llm = ChatGroq(
            model=os.getenv("CURRENT_GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=0,
            max_tokens=512,
            api_key=api_key,
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", DECOMPOSE_SYSTEM_PROMPT),
            ("human", "{question}")
        ])
        chain = prompt | llm
        response = chain.invoke({"question": question})

        content = str(response.content).strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        sub_queries = json.loads(content)
        if not isinstance(sub_queries, list) or len(sub_queries) == 0:
            sub_queries = [question]
    except Exception:
        sub_queries = [question]

    return {"sub_queries": sub_queries}


def multi_target_retrieve(state: MultiTargetState, db_path: str = "chroma_db_test") -> dict:
    """
    2. 다중 대상 서브 검색 노드: 서브 쿼리별로 각각 전체 코퍼스 DB 하이브리드 검색 & 리랭킹을 수행합니다.
    """
    sub_queries = state.get("sub_queries", [state["question"]])
    sub_documents = {}
    for sub_q in sub_queries:
        initial_docs = hybrid_ensemble_search_node(sub_q, db_path=db_path, k=5, k_rrf=60)
        reranked_docs = rerank_documents(sub_q, initial_docs, k=3)
        sub_documents[sub_q] = reranked_docs

    return {"sub_documents": sub_documents}


def synthesize(state: MultiTargetState, mock_response: str = None) -> dict:
    """
    3. 통합 답변 합성 노드: 서브 쿼리별로 수집된 모든 문맥을 종합하여 최종 비교/통합 답변을 산출합니다.
    """
    if mock_response:
        return {"generation": mock_response}

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"generation": "[ERROR] GROQ_API_KEY가 설정되지 않았거나 API 호출 중 오류가 발생했습니다."}

    question = state["question"]
    sub_docs_map = state.get("sub_documents", {})

    formatted_context = ""
    for sub_q, docs in sub_docs_map.items():
        formatted_context += f"\n=== [조사 대상 서브 쿼리: {sub_q}] ===\n"
        for idx, doc in enumerate(docs):
            formatted_context += f"({idx+1}) {doc.get('page_content', '')[:300]}\n"

    try:
        llm = ChatGroq(
            model=os.getenv("CURRENT_GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=0,
            max_tokens=1024,
            api_key=api_key,
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYNTHESIZE_SYSTEM_PROMPT),
            ("human", "Contexts:\n{context}\n\nMain Question: {question}\n\nAnswer:")
        ])
        chain = prompt | llm
        response = chain.invoke({"context": formatted_context, "question": question})
        return {"generation": str(response.content)}
    except Exception as e:
        return {"generation": f"[ERROR] GROQ_API_KEY가 설정되지 않았거나 API 호출 중 오류가 발생했습니다: {e}"}
