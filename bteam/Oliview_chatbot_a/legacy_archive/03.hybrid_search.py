# uv run python 03.hybrid_search.py

"""
Oliview 하이브리드 검색
---------------------------------------------------------------
전체 흐름
---------------------------------------------------------------
사용자 질문
├─ 질문 원문 ───────────────> Chroma 벡터 검색
└─ Kiwi 키워드 추출 ───────> BM25 검색
                                  │
                    Chroma 결과 + BM25 결과
                                  │
                               RRF 결합
                                  │
                         최종 검색 결과 반환

-------------------------------------------------------------
필요 패키지
-------------------------------------------------------------
uv add langchain-chroma langchain-huggingface kiwipiepy rank-bm25 python-dotenv


-------------------------------------------------------------
질문입력시 검색과정
-------------------------------------------------------------
질문: 건성 피부에 촉촉하고 지속력이 좋은 쿠션 추천해줘

Chroma:
질문 원문 전체를 임베딩하여 의미가 비슷한 문장 검색

BM25:
Kiwi → 건성, 피부, 촉촉, 지속력, 쿠션, 추천
추출 키워드로 정확히 일치하는 문장 검색

RRF:
Chroma 순위와 BM25 순위를 합산하여 최종 순위 결정

-------------------------------------------------------------
RRF 점수
-------------------------------------------------------------
RRF 점수 = 1 / (60 + Chroma 순위)
         + 1 / (60 + BM25 순위)

"""




import os
import sys
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from kiwipiepy import Kiwi
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi


# ============================================================
# [1] 프로젝트 최상위 경로 찾기
# ============================================================

def get_project_root() -> str:
    current = os.path.abspath(os.path.dirname(__file__))

    if (
        os.path.exists(os.path.join(current, "pyproject.toml"))
        or os.path.exists(os.path.join(current, "common"))
        or os.path.exists(os.path.join(current, "evaluator"))
    ):
        return current

    parent = os.path.abspath(os.path.join(current, ".."))

    if (
        os.path.exists(os.path.join(parent, "pyproject.toml"))
        or os.path.exists(os.path.join(parent, "common"))
        or os.path.exists(os.path.join(parent, "evaluator"))
    ):
        return parent

    return current


ROOT_DIR = get_project_root()

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from common.utils import get_bge_m3_device


load_dotenv(os.path.join(ROOT_DIR, ".env"))


# ============================================================
# [2] 기본 설정
# ============================================================

LOCAL_MODEL_PATH = os.path.join(
    ROOT_DIR,
    "models",
    "embeddings",
    "bge-m3",
)

CHROMA_DB_PATH = os.path.join(
    ROOT_DIR,
    "chroma_db_oliview",
)

COLLECTION_NAME = "oliview_review_sentences"

# 각 검색 방식에서 먼저 가져올 후보 수
DEFAULT_CANDIDATE_K = 20

# RRF 결합 후 사용자에게 보여줄 최종 결과 수
DEFAULT_FINAL_K = 5

# 일반적으로 60을 사용
RRF_K = 60

EMBEDDING_BATCH_SIZE = 16


# ============================================================
# [3] 검색 결과 자료형
# ============================================================

@dataclass
class SearchItem:
    document_id: str
    text: str
    metadata: dict[str, Any]
    vector_rank: int | None = None
    vector_distance: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    rrf_score: float = 0.0


# ============================================================
# [4] Kiwi 형태소 분석기
# ============================================================

_KIWI: Kiwi | None = None


def get_kiwi() -> Kiwi:
    global _KIWI

    if _KIWI is None:
        print("[INFO] Kiwi 형태소 분석기 로드 중...")
        _KIWI = Kiwi()
        print("[INFO] Kiwi 형태소 분석기 준비 완료")

    return _KIWI


def extract_keywords(text: str) -> list[str]:
    """
    BM25 검색에 사용할 핵심 키워드를 추출합니다.

    사용 품사:
    - NNG: 일반 명사
    - NNP: 고유 명사
    - SL : 영어
    - SN : 숫자
    - VA : 형용사
    - VV : 동사

    예:
    "건성 피부에 촉촉한 쿠션 추천해줘"
    -> ["건성", "피부", "촉촉", "쿠션", "추천"]
    """

    cleaned_text = text.strip()

    if not cleaned_text:
        return []

    try:
        kiwi = get_kiwi()
        tokens = kiwi.tokenize(cleaned_text)

        allowed_tags = {
            "NNG",
            "NNP",
            "SL",
            "SN",
            "VA",
            "VV",
        }

        keywords: list[str] = []

        for token in tokens:
            if token.tag not in allowed_tags:
                continue

            word = token.form.strip().lower()

            if not word:
                continue

            # 한 글자 명사 노이즈를 줄이되 영문·숫자는 허용
            if len(word) == 1 and token.tag in {"NNG", "NNP"}:
                continue

            keywords.append(word)

        if keywords:
            return keywords

    except Exception as error:
        print(f"[WARNING] Kiwi 키워드 추출 실패: {error}")

    # Kiwi 실패 또는 키워드가 없을 때의 안전한 대체 처리
    return [
        word.lower()
        for word in cleaned_text.split()
        if word.strip()
    ]


def tokenize_document(text: str) -> list[str]:
    """
    BM25에 등록할 리뷰 문장도 질문과 같은 방식으로 토큰화합니다.
    """

    return extract_keywords(text)


# ============================================================
# [5] BGE-M3 임베딩 모델 생성
# ============================================================

def is_local_model_ready(model_path: str) -> bool:
    required_files = [
        os.path.join(model_path, "modules.json"),
        os.path.join(model_path, "config.json"),
    ]

    return all(os.path.isfile(path) for path in required_files)


def create_embedding_model():
    server_host = os.getenv("SERVER_HOST")
    embedding_base_url = os.getenv("EMBEDDING_BASE_URL")

    if server_host or embedding_base_url or not is_local_model_ready(LOCAL_MODEL_PATH):
        try:
            from common.embedding_client import HttpBgeM3Embeddings
            print("\n" + "=" * 90)
            print("[BGE-M3 HTTP 원격 임베딩 클라이언트 로드]")
            print("=" * 90)
            embeddings = HttpBgeM3Embeddings()
            print("[INFO] BGE-M3 HTTP 원격 임베딩 모델 준비 완료")
            return embeddings
        except Exception as e:
            if not is_local_model_ready(LOCAL_MODEL_PATH):
                raise RuntimeError(f"원격 임베딩 및 로컬 임베딩 모두 실패: {e}") from e

    if not is_local_model_ready(LOCAL_MODEL_PATH):
        raise FileNotFoundError(
            "\nBGE-M3 로컬 모델을 찾지 못했습니다.\n"
            f"확인 경로: {LOCAL_MODEL_PATH}\n\n"
            "01.build_chroma_db.py 실행 결과를 확인해주세요."
        )

    device = get_bge_m3_device()

    print("\n" + "=" * 90)
    print("[BGE-M3 로컬 임베딩 모델 로드]")
    print("=" * 90)
    print(f"모델 경로 : {LOCAL_MODEL_PATH}")
    print(f"사용 장치 : {device}")
    print("=" * 90)

    embeddings = HuggingFaceEmbeddings(
        model_name=LOCAL_MODEL_PATH,
        model_kwargs={
            "device": device,
            "local_files_only": True,
        },
        encode_kwargs={
            "normalize_embeddings": True,
            "batch_size": EMBEDDING_BATCH_SIZE,
        },
    )

    print("[INFO] BGE-M3 임베딩 모델 준비 완료")

    return embeddings


# ============================================================
# [6] Chroma DB 불러오기
# ============================================================

def load_vector_store(
    embeddings: HuggingFaceEmbeddings,
) -> Chroma:
    if not os.path.isdir(CHROMA_DB_PATH):
        raise FileNotFoundError(
            "\nChroma DB 폴더를 찾지 못했습니다.\n"
            f"확인 경로: {CHROMA_DB_PATH}"
        )

    chroma_sqlite_path = os.path.join(
        CHROMA_DB_PATH,
        "chroma.sqlite3",
    )

    if not os.path.isfile(chroma_sqlite_path):
        raise FileNotFoundError(
            "\nchroma.sqlite3 파일을 찾지 못했습니다.\n"
            f"확인 경로: {chroma_sqlite_path}"
        )

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DB_PATH,
        embedding_function=embeddings,
        collection_metadata={
            "hnsw:space": "cosine",
        },
    )

    stored_count = vector_store._collection.count()

    print("\n" + "=" * 90)
    print("[Oliview Chroma DB 불러오기]")
    print("=" * 90)
    print(f"Chroma 경로 : {CHROMA_DB_PATH}")
    print(f"컬렉션명    : {COLLECTION_NAME}")
    print(f"저장 문장 수: {stored_count:,}개")
    print("=" * 90)

    if stored_count == 0:
        raise RuntimeError(
            "Chroma 컬렉션에 저장된 문장이 없습니다."
        )

    return vector_store


# ============================================================
# [7] Chroma 전체 문장으로 BM25 검색기 생성
# ============================================================

class ChromaBM25Index:
    """
    Chroma에 저장된 모든 리뷰 문장을 가져와
    메모리에 BM25 인덱스를 생성합니다.

    주의:
    - Chroma DB를 변경한 뒤에는 이 파일을 다시 실행해야
      BM25 인덱스도 최신 데이터로 다시 생성됩니다.
    """

    def __init__(self, vector_store: Chroma):
        self.vector_store = vector_store
        self.document_ids: list[str] = []
        self.documents: list[str] = []
        self.metadatas: list[dict[str, Any]] = []
        self.tokenized_corpus: list[list[str]] = []
        self.bm25: BM25Okapi | None = None

        self._build()

    def _build(self) -> None:
        print("\n" + "=" * 90)
        print("[BM25 인덱스 생성]")
        print("=" * 90)

        collection_data = self.vector_store._collection.get(
            include=[
                "documents",
                "metadatas",
            ]
        )

        ids = collection_data.get("ids") or []
        documents = collection_data.get("documents") or []
        metadatas = collection_data.get("metadatas") or []

        if not documents:
            raise RuntimeError(
                "BM25에 등록할 Chroma 문장이 없습니다."
            )

        valid_rows: list[tuple[str, str, dict[str, Any]]] = []

        for document_id, document, metadata in zip(
            ids,
            documents,
            metadatas,
        ):
            if document is None:
                continue

            cleaned_document = str(document).strip()

            if not cleaned_document:
                continue

            valid_rows.append(
                (
                    str(document_id),
                    cleaned_document,
                    metadata or {},
                )
            )

        if not valid_rows:
            raise RuntimeError(
                "BM25에 등록할 유효한 문장이 없습니다."
            )

        self.document_ids = [
            row[0]
            for row in valid_rows
        ]

        self.documents = [
            row[1]
            for row in valid_rows
        ]

        self.metadatas = [
            row[2]
            for row in valid_rows
        ]

        print(f"BM25 등록 대상: {len(self.documents):,}개 문장")
        print("[INFO] Kiwi로 전체 문장 토큰화 중...")

        self.tokenized_corpus = [
            tokenize_document(document)
            for document in self.documents
        ]

        # 토큰이 하나도 없는 문장은 원문 공백 분리로 보완
        self.tokenized_corpus = [
            tokens if tokens else document.lower().split()
            for tokens, document in zip(
                self.tokenized_corpus,
                self.documents,
            )
        ]

        self.bm25 = BM25Okapi(
            self.tokenized_corpus
        )

        print("[INFO] BM25 인덱스 생성 완료")
        print("=" * 90)

    def search(
        self,
        query_keywords: list[str],
        top_k: int,
    ) -> list[SearchItem]:
        if self.bm25 is None:
            raise RuntimeError(
                "BM25 인덱스가 준비되지 않았습니다."
            )

        if not query_keywords:
            return []

        actual_top_k = min(
            top_k,
            len(self.documents),
        )

        scores = self.bm25.get_scores(
            query_keywords
        )

        ranked_indexes = sorted(
            range(len(scores)),
            key=lambda index: float(scores[index]),
            reverse=True,
        )

        results: list[SearchItem] = []

        for index in ranked_indexes:
            score = float(scores[index])

            # 검색어와 겹치는 핵심 단어가 전혀 없으면 제외
            if score <= 0:
                continue

            results.append(
                SearchItem(
                    document_id=self.document_ids[index],
                    text=self.documents[index],
                    metadata=self.metadatas[index],
                    bm25_rank=len(results) + 1,
                    bm25_score=score,
                )
            )

            if len(results) >= actual_top_k:
                break

        return results


# ============================================================
# [8] Chroma 벡터 검색
# ============================================================

def search_chroma(
    vector_store: Chroma,
    embeddings: HuggingFaceEmbeddings,
    query: str,
    top_k: int,
) -> list[SearchItem]:
    cleaned_query = query.strip()

    if not cleaned_query:
        return []

    collection_count = vector_store._collection.count()

    actual_top_k = min(
        top_k,
        collection_count,
    )

    query_embedding = embeddings.embed_query(
        cleaned_query
    )

    raw_results = vector_store._collection.query(
        query_embeddings=[query_embedding],
        n_results=actual_top_k,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    ids = (raw_results.get("ids") or [[]])[0]
    documents = (raw_results.get("documents") or [[]])[0]
    metadatas = (raw_results.get("metadatas") or [[]])[0]
    distances = (raw_results.get("distances") or [[]])[0]

    results: list[SearchItem] = []

    for rank, (
        document_id,
        document,
        metadata,
        distance,
    ) in enumerate(
        zip(
            ids,
            documents,
            metadatas,
            distances,
        ),
        start=1,
    ):
        results.append(
            SearchItem(
                document_id=str(document_id),
                text=str(document or "").strip(),
                metadata=metadata or {},
                vector_rank=rank,
                vector_distance=float(distance),
            )
        )

    return results


# ============================================================
# [9] RRF 결합
# ============================================================

def reciprocal_rank_fusion(
    vector_results: list[SearchItem],
    bm25_results: list[SearchItem],
    final_k: int,
    rrf_k: int = RRF_K,
) -> list[SearchItem]:
    """
    RRF 점수:
        1 / (rrf_k + 검색 순위)

    같은 문장이 Chroma와 BM25에 모두 나오면
    두 검색 방식의 RRF 점수를 합산합니다.
    """

    fused: dict[str, SearchItem] = {}

    for item in vector_results:
        if item.vector_rank is None:
            continue

        if item.document_id not in fused:
            fused[item.document_id] = SearchItem(
                document_id=item.document_id,
                text=item.text,
                metadata=item.metadata,
            )

        fused_item = fused[item.document_id]

        fused_item.vector_rank = item.vector_rank
        fused_item.vector_distance = item.vector_distance
        fused_item.rrf_score += (
            1.0 / (rrf_k + item.vector_rank)
        )

    for item in bm25_results:
        if item.bm25_rank is None:
            continue

        if item.document_id not in fused:
            fused[item.document_id] = SearchItem(
                document_id=item.document_id,
                text=item.text,
                metadata=item.metadata,
            )

        fused_item = fused[item.document_id]

        fused_item.bm25_rank = item.bm25_rank
        fused_item.bm25_score = item.bm25_score
        fused_item.rrf_score += (
            1.0 / (rrf_k + item.bm25_rank)
        )

    sorted_results = sorted(
        fused.values(),
        key=lambda item: (
            item.rrf_score,
            -(item.vector_distance or 999999.0),
            item.bm25_score or 0.0,
        ),
        reverse=True,
    )

    return sorted_results[:final_k]


# ============================================================
# [10] 하이브리드 검색 전체 실행
# ============================================================

def hybrid_search(
    vector_store: Chroma,
    embeddings: HuggingFaceEmbeddings,
    bm25_index: ChromaBM25Index,
    query: str,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    final_k: int = DEFAULT_FINAL_K,
) -> tuple[
    list[str],
    list[SearchItem],
    list[SearchItem],
    list[SearchItem],
]:
    """
    반환값:
        keywords,
        vector_results,
        bm25_results,
        fused_results
    """

    cleaned_query = query.strip()

    if not cleaned_query:
        return [], [], [], []

    if candidate_k <= 0:
        raise ValueError(
            "candidate_k는 1 이상이어야 합니다."
        )

    if final_k <= 0:
        raise ValueError(
            "final_k는 1 이상이어야 합니다."
        )

    # 1. 질문 원문으로 Chroma 의미 검색
    vector_results = search_chroma(
        vector_store=vector_store,
        embeddings=embeddings,
        query=cleaned_query,
        top_k=candidate_k,
    )

    # 2. 질문에서 Kiwi 키워드 추출
    keywords = extract_keywords(
        cleaned_query
    )

    # 3. 추출된 키워드로 BM25 검색
    bm25_results = bm25_index.search(
        query_keywords=keywords,
        top_k=candidate_k,
    )

    # 4. 두 검색 결과를 RRF로 결합
    fused_results = reciprocal_rank_fusion(
        vector_results=vector_results,
        bm25_results=bm25_results,
        final_k=final_k,
    )

    return (
        keywords,
        vector_results,
        bm25_results,
        fused_results,
    )


# ============================================================
# [11] 출력 보조 함수
# ============================================================

def metadata_value(
    metadata: dict[str, Any],
    key: str,
    default: str = "-",
) -> str:
    value = metadata.get(key)

    if value is None:
        return default

    text = str(value).strip()

    return text if text else default


def rank_text(rank: int | None) -> str:
    return str(rank) if rank is not None else "-"


def float_text(
    value: float | None,
    digits: int = 6,
) -> str:
    if value is None:
        return "-"

    return f"{value:.{digits}f}"


def print_simple_candidates(
    title: str,
    results: list[SearchItem],
    search_type: str,
) -> None:
    print("\n" + "-" * 100)
    print(title)
    print("-" * 100)

    if not results:
        print("검색 결과가 없습니다.")
        return

    for item in results[:5]:
        preview = item.text.replace(
            "\n",
            " ",
        )[:80]

        if search_type == "vector":
            print(
                f"벡터 {item.vector_rank:>2}위 | "
                f"distance={float_text(item.vector_distance)} | "
                f"{preview}"
            )
        else:
            print(
                f"BM25 {item.bm25_rank:>2}위 | "
                f"score={float_text(item.bm25_score)} | "
                f"{preview}"
            )


def print_final_results(
    query: str,
    keywords: list[str],
    vector_results: list[SearchItem],
    bm25_results: list[SearchItem],
    fused_results: list[SearchItem],
) -> None:
    print("\n" + "#" * 100)
    print("[Oliview 하이브리드 검색]")
    print("#" * 100)
    print(f"사용자 질문       : {query}")
    print(
        "Kiwi 추출 키워드 : "
        + (
            ", ".join(keywords)
            if keywords
            else "-"
        )
    )
    print(f"Chroma 후보 수    : {len(vector_results)}개")
    print(f"BM25 후보 수      : {len(bm25_results)}개")
    print(f"RRF 최종 결과 수  : {len(fused_results)}개")
    print("#" * 100)

    print_simple_candidates(
        title="[Chroma 상위 후보 미리보기]",
        results=vector_results,
        search_type="vector",
    )

    print_simple_candidates(
        title="[BM25 상위 후보 미리보기]",
        results=bm25_results,
        search_type="bm25",
    )

    print("\n" + "#" * 100)
    print("[RRF 최종 결합 결과]")
    print("#" * 100)

    if not fused_results:
        print("최종 검색 결과가 없습니다.")
        return

    for final_rank, item in enumerate(
        fused_results,
        start=1,
    ):
        metadata = item.metadata or {}

        similarity = None

        if item.vector_distance is not None:
            similarity = 1.0 - item.vector_distance

        print("\n" + "=" * 100)
        print(f"[최종 Rank {final_rank}]")
        print("=" * 100)
        print(f"RRF 점수       : {item.rrf_score:.8f}")
        print(
            f"Chroma 순위    : "
            f"{rank_text(item.vector_rank)}"
        )
        print(
            f"Chroma 거리    : "
            f"{float_text(item.vector_distance)}"
        )
        print(
            f"변환 유사도    : "
            f"{float_text(similarity)}"
        )
        print(
            f"BM25 순위      : "
            f"{rank_text(item.bm25_rank)}"
        )
        print(
            f"BM25 점수      : "
            f"{float_text(item.bm25_score)}"
        )
        print("-" * 100)

        print(
            f"상품 ID        : "
            f"{metadata_value(metadata, 'product_id')}"
        )
        print(
            f"상품명         : "
            f"{metadata_value(metadata, 'product_name')}"
        )
        print(
            f"브랜드명       : "
            f"{metadata_value(metadata, 'brand_name')}"
        )
        print(
            f"분석 카테고리  : "
            f"{metadata_value(metadata, 'analysis_category_name')}"
        )
        print(
            f"상품 카테고리  : "
            f"{metadata_value(metadata, 'category_names')}"
        )
        print(
            f"속성           : "
            f"{metadata_value(metadata, 'attribute_name')}"
        )
        print(
            f"감성           : "
            f"{metadata_value(metadata, 'sentiment')}"
        )
        print(
            f"리뷰 작성일    : "
            f"{metadata_value(metadata, 'review_date')}"
        )

        print("-" * 100)
        print("[리뷰 문장]")
        print(item.text)
        print("=" * 100)


# ============================================================
# [12] 숫자 입력 함수
# ============================================================

def input_positive_int(
    message: str,
    default: int,
) -> int:
    raw_value = input(
        f"{message} (기본값 {default}): "
    ).strip()

    if not raw_value:
        return default

    try:
        value = int(raw_value)

    except ValueError:
        print(
            f"[WARNING] 숫자가 아니므로 "
            f"기본값 {default}를 사용합니다."
        )
        return default

    if value <= 0:
        print(
            f"[WARNING] 1 이상이 아니므로 "
            f"기본값 {default}를 사용합니다."
        )
        return default

    return value


# ============================================================
# [13] 대화형 검색
# ============================================================

def run_interactive_search(
    vector_store: Chroma,
    embeddings: HuggingFaceEmbeddings,
    bm25_index: ChromaBM25Index,
) -> None:
    exit_commands = {
        "exit",
        "quit",
        "q",
        "종료",
    }

    print("\n" + "=" * 100)
    print("[Oliview 하이브리드 검색 준비 완료]")
    print("=" * 100)
    print("예시 질문: 건성 피부에 촉촉하고 지속력이 좋은 쿠션 추천해줘")
    print("종료하려면 exit, quit, q 또는 종료를 입력하세요.")
    print("=" * 100)

    while True:
        query = input("\n사용자 질문: ").strip()

        if query.lower() in exit_commands:
            print("\n하이브리드 검색을 종료합니다.")
            break

        if not query:
            print("[WARNING] 질문을 입력해주세요.")
            continue

        candidate_k = input_positive_int(
            "각 검색 방식의 후보 개수",
            DEFAULT_CANDIDATE_K,
        )

        final_k = input_positive_int(
            "RRF 최종 결과 개수",
            DEFAULT_FINAL_K,
        )

        try:
            (
                keywords,
                vector_results,
                bm25_results,
                fused_results,
            ) = hybrid_search(
                vector_store=vector_store,
                embeddings=embeddings,
                bm25_index=bm25_index,
                query=query,
                candidate_k=candidate_k,
                final_k=final_k,
            )

            print_final_results(
                query=query,
                keywords=keywords,
                vector_results=vector_results,
                bm25_results=bm25_results,
                fused_results=fused_results,
            )

        except Exception as error:
            print("\n" + "!" * 100)
            print("[검색 중 오류 발생]")
            print(f"오류 종류: {type(error).__name__}")
            print(f"오류 내용: {error}")
            print("!" * 100)


# ============================================================
# [14] 메인 실행
# ============================================================

def main() -> None:
    try:
        embeddings = create_embedding_model()

        vector_store = load_vector_store(
            embeddings=embeddings,
        )

        # 프로그램 시작 시 Chroma 전체 문장으로 BM25 인덱스를 한 번 생성합니다.
        bm25_index = ChromaBM25Index(
            vector_store=vector_store,
        )

        run_interactive_search(
            vector_store=vector_store,
            embeddings=embeddings,
            bm25_index=bm25_index,
        )

    except KeyboardInterrupt:
        print("\n\n사용자가 실행을 중단했습니다.")

    except Exception as error:
        print("\n" + "=" * 100)
        print("[ERROR] 하이브리드 검색 실행 중 오류가 발생했습니다.")
        print(f"오류 종류: {type(error).__name__}")
        print(f"오류 내용: {error}")
        print("=" * 100)

        raise


if __name__ == "__main__":
    main()