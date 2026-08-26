from langchain_text_splitters import RecursiveCharacterTextSplitter

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100

CHUNK_SEPARATORS = [
    "\n\n",  # 문단
    "\n",    # 줄바꿈
    ". ",    # 문장
    " ",     # 단어
    "",      # 마지막에는 문자 단위로 분할
]

def split_text_into_chunks(text: str, 
                           *, 
                           chunk_size: int = DEFAULT_CHUNK_SIZE,
                           chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
)-> list[str]:
    """긴 문서 하나를 RAG 검색용 청크 여러 개로 나눈다."""

    if not isinstance(text, str):
        raise TypeError("text는 문자열이어야 합니다.")

    if not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size는 1 이상이어야 합니다.")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap은 0 이상이어야 합니다.")

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap은 chunk_size보다 작아야 합니다."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=CHUNK_SEPARATORS,
        length_function=len,
        is_separator_regex=False,
    )

    chunks = splitter.split_text(text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]