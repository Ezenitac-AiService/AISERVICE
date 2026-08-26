"""
Core Data Models for Document Chunking and Hybrid Retrieval
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class Document:
    """원본 실습 문서 엔티티"""
    file_path: str
    file_name: str
    content: str
    document_keywords: List[str] = field(default_factory=list)

@dataclass
class Chunk:
    """분할 청크 엔티티"""
    chunk_id: str
    source_file: str
    chunk_index: int
    text_content: str
    start_char_idx: int = 0
    end_char_idx: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HybridSearchResult:
    """하이브리드 검색 결과 엔티티"""
    chunk_id: str
    source_file: str
    chunk_index: int
    matched_keywords: List[str]
    vector_score: float
    keyword_score: float
    hybrid_score: float
    text_preview: str
    raw_chunk_text: str
