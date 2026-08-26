"""
Document Loader & Chunk Metadata Binding Engine
"""

import os
import re
from typing import List, Dict, Any
from evaluator.models import Document, Chunk
from evaluator.keyword_extractor import ChunkKeywordExtractor

def parse_header_keywords(content: str) -> List[str]:
    """[KEYWORDS: ...] 헤더 태그에서 키워드 목록 파싱"""
    match = re.search(r"\[KEYWORDS:\s*(.*?)\]", content, re.IGNORECASE)
    if match:
        raw_kw = match.group(1)
        keywords = [k.strip() for k in raw_kw.split(",") if k.strip()]
        return keywords
    return []

def load_documents_from_dir(dir_path: str) -> List[Document]:
    """디렉터리 내 txt/md 문서를 로드하고 헤더 키워드를 추출"""
    documents = []
    if not os.path.exists(dir_path):
        return documents

    for fname in sorted(os.listdir(dir_path)):
        if fname.endswith((".txt", ".md")):
            fpath = os.path.join(dir_path, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            header_kws = parse_header_keywords(text)
            doc = Document(
                file_path=fpath,
                file_name=fname,
                content=text,
                document_keywords=header_kws
            )
            documents.append(doc)
    return documents

def load_and_chunk_documents(
    dir_path: str,
    chunk_size: int = 400,
    chunk_overlap: int = 50
) -> List[Chunk]:
    """
    문서 파일들을 로드하고 청크 단위로 분할하여 키워드 메타데이터를 결합합니다.
    """
    documents = load_documents_from_dir(dir_path)
    all_chunks: List[Chunk] = []

    for doc in documents:
        content = doc.content
        file_name = doc.file_name
        doc_kws = list(doc.document_keywords)
        
        # 헤더 키워드가 부족하면 Kiwi 형태소 분석기로 1차 보완
        if len(doc_kws) < 3:
            morph_kws = ChunkKeywordExtractor.extract_morph_keywords(content)
            for kw in morph_kws:
                if kw not in doc_kws:
                    doc_kws.append(kw)

        # 고정 크기 슬라이딩 윈도우 청킹
        idx = 0
        chunk_counter = 0
        str_len = len(content)

        while idx < str_len:
            end_idx = min(idx + chunk_size, str_len)
            chunk_text = content[idx:end_idx].strip()

            if chunk_text:
                chunk_id = f"{file_name}_chunk_{chunk_counter:03d}"
                
                # 청크별 키워드: 문서 전체 키워드 중 해당 청크 본문에 등장하거나 형태소 분석된 키워드 매핑
                chunk_morph_kws = ChunkKeywordExtractor.extract_morph_keywords(chunk_text)
                chunk_kws = list(doc_kws)
                for mk in chunk_morph_kws:
                    if mk not in chunk_kws:
                        chunk_kws.append(mk)

                chunk = Chunk(
                    chunk_id=chunk_id,
                    source_file=file_name,
                    chunk_index=chunk_counter,
                    text_content=chunk_text,
                    start_char_idx=idx,
                    end_char_idx=end_idx,
                    metadata={
                        "source": file_name,
                        "chunk_index": chunk_counter,
                        "keywords": chunk_kws if chunk_kws else ["일반"],
                    }
                )
                all_chunks.append(chunk)
                chunk_counter += 1

            if end_idx >= str_len:
                break
            idx += (chunk_size - chunk_overlap)

    return all_chunks
