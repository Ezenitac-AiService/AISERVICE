"""
RAG Prompt Templates & System Instructions Module
"""

from langchain_core.prompts import ChatPromptTemplate

RAG_SYSTEM_PROMPT = (
    "You are a helpful assistant for question-answering tasks. Use the provided context to answer the user's question accurately in Korean.\n"
    "When asked about concepts, differences, or characteristics, analyze and synthesize their roles based on the definitions and details given in the context.\n"
    "If the provided context contains no relevant information to answer the question at all, state: '제공된 정보에 해당 내용이 없어 답변할 수 없습니다.'"
)

def get_rag_prompt() -> ChatPromptTemplate:
    """
    Returns a unified ChatPromptTemplate for RAG nodes.
    """
    return ChatPromptTemplate.from_messages([
        ("system", RAG_SYSTEM_PROMPT),
        ("human", "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:")
    ])

DECOMPOSE_SYSTEM_PROMPT = """You are an expert query decomposer for RAG systems.
Given a user's question, determine if it involves multiple target concepts, components, or entities to compare/investigate.
If it involves multiple targets, decompose the question into 2-3 specific, independent sub-queries in Korean, each targeting one specific entity/concept.
If it is a single-target question, return a list containing just the original question.

Return ONLY a valid JSON array of strings, for example:
["RAG의 스마트 청킹(Smart Chunking) 기법의 정의 및 특성", "1024차원 BGE-M3 임베딩 모델의 정의 및 특성"]
Do NOT include any markdown code block syntax or extra conversational text."""

SYNTHESIZE_SYSTEM_PROMPT = """You are an expert RAG synthesis assistant.
Your task is to provide a clear, structured, and comprehensive answer to the user's main question in Korean.
You are provided with retrieved contexts for each sub-query/target concept.
Synthesize the information from all sub-query contexts. Compare, contrast, and explain the roles of each target entity clearly based on the provided contexts.
If the contexts contain no relevant information to answer at all, state: '제공된 정보에 해당 내용이 없어 답변할 수 없습니다.'"""
