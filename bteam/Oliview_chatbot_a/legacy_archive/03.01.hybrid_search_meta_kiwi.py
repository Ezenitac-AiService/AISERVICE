# uv run python 03.01.hybrid_search.py


# 메타데이터 사용 -> kiwi이용
#                 (brand_name, analysis_category_name,category_names, attribute_name, sentiment)
                # 1) brand_name	질문과 ChromaDB 브랜드 metadata를 비교하여 추출
                # 2) category_names	Kiwi 키워드 + Category Alias를 이용하여 상품 카테고리 metadata 추출
                # 3) analysis_category_name	상품 카테고리를 찾지 못한 경우 상위 분석 카테고리 추출
                # 4) attribute_name	질문과 속성 metadata를 비교하여 추출
                # 5) sentiment	질문의 긍정/부정 표현으로 저장된 감성 metadata 필터링(감성분석 X)
"""
Oliview 하이브리드 검색
---------------------------------------------------------------
전체 흐름
---------------------------------------------------------------
사용자 질문
    │
    ▼
Kiwi + Chroma metadata 사전
(브랜드 / 카테고리 / 속성 / 감성 조건 추출)
    │
    ▼
Metadata Filter 생성
    │
    ├─ 질문 원문 + 동일 Filter ───────> Chroma 벡터 검색
    └─ Kiwi 키워드 + 동일 Filter ────> BM25 검색
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
질문 입력 예시
-------------------------------------------------------------
질문: 토리든의 보습력이 좋은 토너 추천해줘

Metadata Filter:
- brand_name = 토리든
- category_names = 토너가 포함된 실제 metadata 값
- attribute_name = 보습 관련 속성

Chroma:
- 위 Filter가 적용된 문장만 대상으로
- 질문 원문 전체를 임베딩하여 의미가 비슷한 문장 검색

BM25:
- 위 Filter가 적용된 동일한 문장 집합만 대상으로
- Kiwi가 추출한 키워드로 단어 일치도가 높은 문장 검색

RRF:
- Chroma 순위와 BM25 순위를 합산하여 최종 순위 결정

-------------------------------------------------------------
RRF 점수
-------------------------------------------------------------
RRF 점수 = 1 / (60 + Chroma 순위)
         + 1 / (60 + BM25 순위)
"""

import os
import re
import sys
from dataclasses import dataclass, field
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

# 자동 Metadata Filter에 사용할 필드
EXACT_FILTER_FIELDS = (
    "brand_name",
    "analysis_category_name",
    "attribute_name",
)

# category_names는 쉼표로 여러 카테고리가 저장될 수 있으므로
# 질문에서 하위 카테고리 단어를 찾은 뒤 실제 전체 metadata 값의 $in으로 변환합니다.
CATEGORY_FILTER_FIELD = "category_names"
SENTIMENT_FILTER_FIELD = "sentiment"

# 사용자 표현과 실제 상품 카테고리명의 차이를 보정합니다.
# 왼쪽은 질문에 등장할 수 있는 표현, 오른쪽은 Chroma metadata의 표준 카테고리명입니다.
CATEGORY_ALIASES = {
     # 선케어
    "썬크림": "선크림",
    "선블록": "선크림",
    "썬블록": "선크림",
    "선스크린": "선크림",
    "썬스틱": "선스틱",
    "썬쿠션": "선쿠션",
    "썬스프레이": "선스프레이",
    "썬패치": "선패치",

    # 스킨케어
    "토너": "스킨/토너",
    "스킨토너": "스킨/토너",
    "에센스": "에센스/세럼/앰플",
    "세럼": "에센스/세럼/앰플",
    "앰플": "에센스/세럼/앰플",

    # 클렌징
    "클렌징크림": "클렌징밀크/크림",
    "클렌징밀크": "클렌징밀크/크림",
    "클렌징폼": "클렌징폼/젤",
    "클렌징젤": "클렌징폼/젤",
    "클렌징티슈": "클렌징티슈/패드",
    "클렌징패드": "클렌징티슈/패드",

    # 메이크업
    "파우더": "파우더/팩트",
    "팩트": "파우더/팩트",
    "bb": "BB/CC",
    "cc": "BB/CC",

}


# ============================================================
# [3] 검색 결과 및 Metadata Filter 자료형
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


@dataclass
class MetadataFilterResult:
    """
    field_values:
        실제 metadata 필드별 허용 값 목록입니다.
        예: {"brand_name": ["토리든"], "attribute_name": ["보습"]}

    matched_terms:
        사용자 질문에서 어떤 표현이 매칭됐는지 출력하기 위한 값입니다.

    chroma_where:
        Chroma collection.query(where=...)에 전달할 조건입니다.
    """

    field_values: dict[str, list[str]] = field(default_factory=dict)
    matched_terms: dict[str, list[str]] = field(default_factory=dict)
    chroma_where: dict[str, Any] | None = None

    @property
    def is_active(self) -> bool:
        return bool(self.field_values)


# ============================================================
# [4] 공통 문자열 정리
# ============================================================

def normalize_for_match(value: Any) -> str:
    """
    질문과 metadata 값을 비교하기 위한 정규화입니다.
    대소문자와 공백 차이를 줄이되, 실제 metadata 원본 값은 변경하지 않습니다.
    """

    text = str(value or "").strip().lower()
    return re.sub(r"\s+", "", text)


def unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        cleaned = str(value or "").strip()

        if not cleaned or cleaned in seen:
            continue

        seen.add(cleaned)
        result.append(cleaned)

    return result


# ============================================================
# [5] Kiwi 형태소 분석기
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
    BM25 검색 및 metadata 조건 탐색에 사용할 핵심 키워드를 추출합니다.

    사용 품사:
    - NNG: 일반 명사
    - NNP: 고유 명사
    - SL : 영어
    - SN : 숫자
    - VA : 형용사
    - VV : 동사
    - XR : 어근
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
            "XR",
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
    """BM25에 등록할 리뷰 문장도 질문과 같은 방식으로 토큰화합니다."""

    return extract_keywords(text)


# ============================================================
# [6] BGE-M3 임베딩 모델 생성
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
    print("[BGE-M3 임베딩 모델 로드]")
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
# [7] Chroma DB 불러오기
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
# [8] Chroma 전체 문장으로 BM25 검색기 생성
# ============================================================

class ChromaBM25Index:
    """
    Chroma에 저장된 모든 리뷰 문장과 metadata를 가져와
    메모리에 BM25 인덱스를 생성합니다.

    Metadata Filter가 생성되면 BM25 점수를 전체 문서에 계산하더라도,
    실제 순위 후보에는 Filter 조건과 일치하는 문장만 포함합니다.
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

        collection = self.vector_store._collection
        total_count = collection.count()
        batch_size = 1000

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        print(
            f"[INFO] Chroma 전체 문장 배치 로드 시작 "
            f"(총 {total_count:,}개, 배치 {batch_size:,}개)"
        )

        for offset in range(0, total_count, batch_size):
            batch_data = collection.get(
                limit=batch_size,
                offset=offset,
                include=[
                    "documents",
                    "metadatas",
                ],
            )

            batch_ids = batch_data.get("ids") or []
            batch_documents = batch_data.get("documents") or []
            batch_metadatas = batch_data.get("metadatas") or []

            ids.extend(str(document_id) for document_id in batch_ids)
            documents.extend(batch_documents)
            metadatas.extend(batch_metadatas)

            loaded_count = min(
                offset + len(batch_ids),
                total_count,
            )

            print(
                f"\r[INFO] Chroma 문장 로드: "
                f"{loaded_count:,}/{total_count:,}개",
                end="",
                flush=True,
            )

        print()

        if len(ids) != len(documents) or len(documents) != len(metadatas):
            raise RuntimeError(
                "Chroma 배치 조회 결과의 ids/documents/metadatas 개수가 서로 다릅니다. "
                f"ids={len(ids):,}, documents={len(documents):,}, "
                f"metadatas={len(metadatas):,}"
            )

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

        self.document_ids = [row[0] for row in valid_rows]
        self.documents = [row[1] for row in valid_rows]
        self.metadatas = [row[2] for row in valid_rows]

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

        self.bm25 = BM25Okapi(self.tokenized_corpus)

        print("[INFO] BM25 인덱스 생성 완료")
        print("=" * 90)

    def metadata_values(self, key: str) -> list[str]:
        """특정 metadata 필드의 실제 저장 값을 중복 없이 반환합니다."""

        return unique_nonempty([
            str(metadata.get(key, ""))
            for metadata in self.metadatas
        ])

    @staticmethod
    def metadata_matches(
        metadata: dict[str, Any],
        field_values: dict[str, list[str]],
    ) -> bool:
        """
        서로 다른 필드는 AND, 같은 필드 안의 여러 값은 OR로 비교합니다.

        예:
        brand_name = ["토리든"]
        attribute_name = ["보습", "지속력"]

        → 토리든이면서 속성이 보습 또는 지속력인 문장
        """

        for key, allowed_values in field_values.items():
            metadata_value = str(metadata.get(key, "")).strip()

            if metadata_value not in allowed_values:
                return False

        return True

    def count_filtered_documents(
        self,
        field_values: dict[str, list[str]],
    ) -> int:
        if not field_values:
            return len(self.documents)

        return sum(
            1
            for metadata in self.metadatas
            if self.metadata_matches(metadata, field_values)
        )

    def search(
        self,
        query_keywords: list[str],
        top_k: int,
        metadata_filter: MetadataFilterResult | None = None,
    ) -> list[SearchItem]:
        if self.bm25 is None:
            raise RuntimeError(
                "BM25 인덱스가 준비되지 않았습니다."
            )

        if not query_keywords:
            return []

        field_values = (
            metadata_filter.field_values
            if metadata_filter is not None
            else {}
        )

        eligible_indexes = [
            index
            for index, metadata in enumerate(self.metadatas)
            if self.metadata_matches(metadata, field_values)
        ]

        if not eligible_indexes:
            return []

        actual_top_k = min(top_k, len(eligible_indexes))

        scores = self.bm25.get_scores(query_keywords)

        ranked_indexes = sorted(
            eligible_indexes,
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
# [9] 질문에서 Metadata Filter 생성
# ============================================================

class MetadataFilterExtractor:
    """
    Chroma에 실제 저장된 metadata 값을 사전처럼 사용합니다.

    별도의 브랜드·카테고리 하드코딩 없이,
    현재 Chroma DB에 들어 있는 값 중 질문에 등장한 값을 찾습니다.
    """

    def __init__(self, bm25_index: ChromaBM25Index):
        self.bm25_index = bm25_index

        self.field_vocabularies: dict[str, list[str]] = {
            key: sorted(
                bm25_index.metadata_values(key),
                key=lambda value: len(normalize_for_match(value)),
                reverse=True,
            )
            for key in EXACT_FILTER_FIELDS
        }

        self.category_full_values = sorted(
            bm25_index.metadata_values(CATEGORY_FILTER_FIELD),
            key=lambda value: len(normalize_for_match(value)),
            reverse=True,
        )

        self.category_token_to_full_values = (
            self._build_category_token_map()
        )

        self.sentiment_values = bm25_index.metadata_values(
            SENTIMENT_FILTER_FIELD
        )

# 추가시작
        print("=" * 50)
        print("[DEBUG] BB 토큰")

        for token in sorted(self.category_token_to_full_values):
            if "bb" in token.lower():
                print(repr(token), "->", self.category_token_to_full_values[token])
# 추가끝


        print("\n" + "=" * 90)
        print("[Metadata Filter 사전 준비]")
   

        print("=" * 90)
        print(
            f"브랜드 값        : "
            f"{len(self.field_vocabularies.get('brand_name', [])):,}개"
        )
        print(
            f"분석 카테고리 값 : "
            f"{len(self.field_vocabularies.get('analysis_category_name', [])):,}개"
        )
        print(
            f"속성 값          : "
            f"{len(self.field_vocabularies.get('attribute_name', [])):,}개"
        )
        print(
            f"상품 카테고리 값 : "
            f"{len(self.category_full_values):,}개"
        )
        print("=" * 90)

    def _build_category_token_map(self) -> dict[str, set[str]]:
        """
        category_names가 "메이크업, 베이스메이크업, 쿠션"처럼 저장된 경우,
        질문의 "쿠션"을 실제 전체 metadata 값 목록으로 변환합니다.
        """

        token_map: dict[str, set[str]] = {}

        for full_value in self.category_full_values:
            # category_names는 쉼표로만 여러 단계가 구분됩니다.
            # "/"는 "클렌징밀크/크림"처럼 실제 카테고리명의 일부이므로 분리하지 않습니다.
            parts = full_value.split(",")

            for part in parts:
                cleaned_part = str(part).strip()
                normalized_part = normalize_for_match(cleaned_part)

                # 한 글자 토큰은 오탐이 많으므로 제외
                if len(normalized_part) < 2:
                    continue

                token_map.setdefault(
                    cleaned_part,
                    set(),
                ).add(full_value)

        return token_map

    @staticmethod
    def _match_known_values(
        query_normalized: str,
        vocabulary: list[str],
        allow_multiple: bool,
    ) -> tuple[list[str], list[str]]:
        matched_values: list[str] = []
        matched_terms: list[str] = []

        for value in vocabulary:
            normalized_value = normalize_for_match(value)

            if len(normalized_value) < 2:
                continue

            if normalized_value not in query_normalized:
                continue

            # 더 긴 값이 이미 선택된 경우 그 안에 포함되는 짧은 값은 제외
            if any(
                normalized_value in normalize_for_match(existing)
                for existing in matched_values
            ):
                continue

            matched_values.append(value)
            matched_terms.append(value)

            if not allow_multiple:
                break

        return matched_values, matched_terms

    def _extract_category_filter(
        self,
        query: str,
        query_keywords: list[str],
    ) -> tuple[list[str], list[str]]:
        """
        쉼표로 분리된 카테고리 항목과 질문 키워드를 정확히 비교합니다.

        예:
        - metadata: "메이크업, 베이스메이크업, 쿠션"
        - 질문 키워드: "쿠션"
          → "쿠션" 항목과 정확히 일치

        "크림"이 "썬크림" 안에 들어 있다는 이유만으로 매칭하지 않습니다.
        대신 CATEGORY_ALIASES를 통해 "썬크림"을 "선크림"으로 정규화합니다.
        """

        # Kiwi 키워드와 공백 단위 원문 표현을 함께 사용합니다.
        raw_terms = list(query_keywords)
        raw_terms.extend(
            term
            for term in re.split(r"[\s,!?./()\[\]{}]+", query)
            if term.strip()
        )

        # 표준 카테고리명 -> 질문에 실제로 등장한 표현
        normalized_term_to_original: dict[str, str] = {}

        for raw_term in raw_terms:
            original_term = str(raw_term or "").strip()
            normalized_term = normalize_for_match(original_term)

            if len(normalized_term) < 2:
                continue

            canonical_term = CATEGORY_ALIASES.get(
                normalized_term,
                normalized_term,
            )
            canonical_normalized = normalize_for_match(canonical_term)

            normalized_term_to_original.setdefault(
                canonical_normalized,
                original_term,
            )

        # "클렌징 크림"처럼 띄어 쓴 복합 별칭도 질문 전체에서 찾습니다.
        # normalize_for_match()가 공백을 제거하므로 "클렌징크림"으로 비교됩니다.
        query_normalized = normalize_for_match(query)

        for alias, canonical in CATEGORY_ALIASES.items():
            normalized_alias = normalize_for_match(alias)

            if normalized_alias not in query_normalized:
                continue

            canonical_normalized = normalize_for_match(canonical)
            normalized_term_to_original.setdefault(
                canonical_normalized,
                alias,
            )

        matched_tokens: list[str] = []
        matched_full_values: set[str] = set()

        sorted_tokens = sorted(
            self.category_token_to_full_values,
            key=lambda value: len(normalize_for_match(value)),
            reverse=True,
        )

        for token in sorted_tokens:
            normalized_token = normalize_for_match(token)

            # 문자열 부분 포함이 아니라 질문에서 추출한 하나의 표현과 정확히 일치해야 합니다.
            if normalized_token not in normalized_term_to_original:
                continue

            matched_tokens.append(
                normalized_term_to_original[normalized_token]
            )
            matched_full_values.update(
                self.category_token_to_full_values[token]
            )

            # 카테고리는 가장 구체적인 하나를 우선 사용합니다.
            break

        return (
            sorted(matched_full_values),
            matched_tokens,
        )

    def _extract_sentiment_filter(
        self,
        query_normalized: str,
    ) -> tuple[list[str], list[str]]:
        if not self.sentiment_values:
            return [], []

        positive_terms = (
            "긍정리뷰",
            "긍정의견",
            "장점",
            "만족한",
            "만족리뷰",
        )
        negative_terms = (
            "부정리뷰",
            "부정의견",
            "단점",
            "불만",
            "아쉬운점",
        )

        target_kind: str | None = None
        matched_term: str | None = None

        for term in positive_terms:
            if normalize_for_match(term) in query_normalized:
                target_kind = "positive"
                matched_term = term
                break

        if target_kind is None:
            for term in negative_terms:
                if normalize_for_match(term) in query_normalized:
                    target_kind = "negative"
                    matched_term = term
                    break

        if target_kind is None:
            return [], []

        aliases = {
            "positive": ("긍정", "positive", "pos"),
            "negative": ("부정", "negative", "neg"),
        }

        matched_values = [
            value
            for value in self.sentiment_values
            if any(
                alias in normalize_for_match(value)
                for alias in aliases[target_kind]
            )
        ]

        return matched_values, [matched_term] if matched_values else []

    @staticmethod
    def _build_chroma_where(
        field_values: dict[str, list[str]],
    ) -> dict[str, Any] | None:
        conditions: list[dict[str, Any]] = []

        for key, values in field_values.items():
            cleaned_values = unique_nonempty(values)

            if not cleaned_values:
                continue

            if len(cleaned_values) == 1:
                conditions.append({
                    key: {"$eq": cleaned_values[0]}
                })
            else:
                conditions.append({
                    key: {"$in": cleaned_values}
                })

        if not conditions:
            return None

        if len(conditions) == 1:
            return conditions[0]

        return {"$and": conditions}

    def extract(self, query: str) -> MetadataFilterResult:
        query_normalized = normalize_for_match(query)

        if not query_normalized:
            return MetadataFilterResult()

        field_values: dict[str, list[str]] = {}
        matched_terms: dict[str, list[str]] = {}

        # 1. 브랜드는 질문에 명확히 등장하면 항상 사용합니다.
        brand_values, brand_terms = self._match_known_values(
            query_normalized=query_normalized,
            vocabulary=self.field_vocabularies.get("brand_name", []),
            allow_multiple=False,
        )

        if brand_values:
            field_values["brand_name"] = brand_values
            matched_terms["brand_name"] = brand_terms

        # 2. 구체적인 상품 카테고리를 먼저 찾습니다.
        #    예: 쿠션, 선크림, 클렌징밀크/크림
        query_keywords = extract_keywords(query)
        category_values, category_terms = self._extract_category_filter(
            query=query,
            query_keywords=query_keywords,
        )

        if category_values:
            field_values[CATEGORY_FILTER_FIELD] = category_values
            matched_terms[CATEGORY_FILTER_FIELD] = category_terms

        # 3. 구체적인 상품 카테고리를 찾지 못했을 때만
        #    분석 카테고리를 넓은 범주의 보조 필터로 사용합니다.
        #    예: "클렌징 제품 추천" -> analysis_category_name = 클렌징
        if not category_values:
            analysis_values, analysis_terms = self._match_known_values(
                query_normalized=query_normalized,
                vocabulary=self.field_vocabularies.get(
                    "analysis_category_name",
                    [],
                ),
                allow_multiple=False,
            )

            if analysis_values:
                field_values["analysis_category_name"] = analysis_values
                matched_terms["analysis_category_name"] = analysis_terms

        # 4. 속성은 한 질문에 여러 개가 등장할 수 있으므로 OR 조건으로 사용합니다.
        attribute_values, attribute_terms = self._match_known_values(
            query_normalized=query_normalized,
            vocabulary=self.field_vocabularies.get(
                "attribute_name",
                [],
            ),
            allow_multiple=True,
        )

        if attribute_values:
            field_values["attribute_name"] = attribute_values
            matched_terms["attribute_name"] = attribute_terms

        # 5. 긍정/부정처럼 감성이 명시된 경우에만 감성 필터를 사용합니다.
        sentiment_values, sentiment_terms = (
            self._extract_sentiment_filter(query_normalized)
        )

        if sentiment_values:
            field_values[SENTIMENT_FILTER_FIELD] = sentiment_values
            matched_terms[SENTIMENT_FILTER_FIELD] = sentiment_terms

        return MetadataFilterResult(
            field_values=field_values,
            matched_terms=matched_terms,
            chroma_where=self._build_chroma_where(field_values),
        )


# ============================================================
# [10] Chroma 벡터 검색
# ============================================================

def search_chroma(
    vector_store: Chroma,
    embeddings: HuggingFaceEmbeddings,
    query: str,
    top_k: int,
    metadata_filter: MetadataFilterResult | None = None,
) -> list[SearchItem]:
    cleaned_query = query.strip()

    if not cleaned_query:
        return []

    collection_count = vector_store._collection.count()
    actual_top_k = min(top_k, collection_count)

    query_embedding = embeddings.embed_query(cleaned_query)

    query_kwargs: dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": actual_top_k,
        "include": [
            "documents",
            "metadatas",
            "distances",
        ],
    }

    if (
        metadata_filter is not None
        and metadata_filter.chroma_where is not None
    ):
        query_kwargs["where"] = metadata_filter.chroma_where

    raw_results = vector_store._collection.query(**query_kwargs)

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
# [11] RRF 결합
# ============================================================

def reciprocal_rank_fusion(
    vector_results: list[SearchItem],
    bm25_results: list[SearchItem],
    final_k: int,
    rrf_k: int = RRF_K,
) -> list[SearchItem]:
    """
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
# [12] 하이브리드 검색 전체 실행
# ============================================================

def hybrid_search(
    vector_store: Chroma,
    embeddings: HuggingFaceEmbeddings,
    bm25_index: ChromaBM25Index,
    filter_extractor: MetadataFilterExtractor,
    query: str,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    final_k: int = DEFAULT_FINAL_K,
) -> tuple[
    list[str],
    MetadataFilterResult,
    int,
    list[SearchItem],
    list[SearchItem],
    list[SearchItem],
]:
    """
    반환값:
        keywords,
        metadata_filter,
        filtered_document_count,
        vector_results,
        bm25_results,
        fused_results
    """

    cleaned_query = query.strip()

    if not cleaned_query:
        return (
            [],
            MetadataFilterResult(),
            0,
            [],
            [],
            [],
        )

    if candidate_k <= 0:
        raise ValueError(
            "candidate_k는 1 이상이어야 합니다."
        )

    if final_k <= 0:
        raise ValueError(
            "final_k는 1 이상이어야 합니다."
        )

    # 1. 질문에서 Kiwi 키워드 추출
    keywords = extract_keywords(cleaned_query)

    # 2. 실제 Chroma metadata 값을 사전으로 사용하여 Filter 생성
    metadata_filter = filter_extractor.extract(cleaned_query)

    filtered_document_count = bm25_index.count_filtered_documents(
        metadata_filter.field_values
    )

    # 3. 질문 원문 + Metadata Filter로 Chroma 의미 검색
    vector_results = search_chroma(
        vector_store=vector_store,
        embeddings=embeddings,
        query=cleaned_query,
        top_k=candidate_k,
        metadata_filter=metadata_filter,
    )

    # 4. 동일한 Metadata Filter 후보에서 Kiwi 키워드로 BM25 검색
    bm25_results = bm25_index.search(
        query_keywords=keywords,
        top_k=candidate_k,
        metadata_filter=metadata_filter,
    )

    # 5. 두 검색 결과를 RRF로 결합
    fused_results = reciprocal_rank_fusion(
        vector_results=vector_results,
        bm25_results=bm25_results,
        final_k=final_k,
    )

    return (
        keywords,
        metadata_filter,
        filtered_document_count,
        vector_results,
        bm25_results,
        fused_results,
    )


# ============================================================
# [13] 출력 보조 함수
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


def print_metadata_filter(
    metadata_filter: MetadataFilterResult,
    filtered_document_count: int,
) -> None:
    print("\n" + "-" * 100)
    print("[Metadata Filter]")
    print("-" * 100)

    if not metadata_filter.is_active:
        print("질문에서 명확한 metadata 조건을 찾지 못해 전체 문장을 검색합니다.")
        print(f"검색 대상 문장 수: {filtered_document_count:,}개")
        return

    field_labels = {
        "brand_name": "브랜드",
        "analysis_category_name": "분석 카테고리",
        "category_names": "상품 카테고리",
        "attribute_name": "속성",
        "sentiment": "감성",
    }

    for key, values in metadata_filter.field_values.items():
        label = field_labels.get(key, key)
        terms = metadata_filter.matched_terms.get(key, [])

        # category는 여러 metadata 허용값이므로 줄바꿈해서 출력
        if key == "category_names":
            print(f"{label:<15}:")
            for value in values:
                print(f"{'':<17}- {value}")
        else:
            print(f"{label:<15}: {', '.join(values)}")

        if terms:
            print(f"{'질문 매칭 표현':<15}: {', '.join(terms)}")

    print(f"필터 적용 문장 수 : {filtered_document_count:,}개")
    print(f"Chroma where      : {metadata_filter.chroma_where}")


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
        preview = item.text.replace("\n", " ")[:80]

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
    metadata_filter: MetadataFilterResult,
    filtered_document_count: int,
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
        + (", ".join(keywords) if keywords else "-")
    )
    print(f"필터 적용 문장 수 : {filtered_document_count:,}개")
    print(f"Chroma 후보 수    : {len(vector_results)}개")
    print(f"BM25 후보 수      : {len(bm25_results)}개")
    print(f"RRF 최종 결과 수  : {len(fused_results)}개")
    print("#" * 100)

    print_metadata_filter(
        metadata_filter=metadata_filter,
        filtered_document_count=filtered_document_count,
    )

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
        print(f"Chroma 순위    : {rank_text(item.vector_rank)}")
        print(f"Chroma 거리    : {float_text(item.vector_distance)}")
        print(f"변환 유사도    : {float_text(similarity)}")
        print(f"BM25 순위      : {rank_text(item.bm25_rank)}")
        print(f"BM25 점수      : {float_text(item.bm25_score)}")
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
# [14] 숫자 입력 함수
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
# [15] 대화형 검색
# ============================================================

def run_interactive_search(
    vector_store: Chroma,
    embeddings: HuggingFaceEmbeddings,
    bm25_index: ChromaBM25Index,
    filter_extractor: MetadataFilterExtractor,
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
    print("예시 질문: 토리든의 보습력이 좋은 토너 추천해줘")
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
                metadata_filter,
                filtered_document_count,
                vector_results,
                bm25_results,
                fused_results,
            ) = hybrid_search(
                vector_store=vector_store,
                embeddings=embeddings,
                bm25_index=bm25_index,
                filter_extractor=filter_extractor,
                query=query,
                candidate_k=candidate_k,
                final_k=final_k,
            )

            print_final_results(
                query=query,
                keywords=keywords,
                metadata_filter=metadata_filter,
                filtered_document_count=filtered_document_count,
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
# [16] 메인 실행
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

        # BM25 인덱스가 보유한 실제 metadata로 질문 분석 사전을 만듭니다.
        filter_extractor = MetadataFilterExtractor(
            bm25_index=bm25_index,
        )

        run_interactive_search(
            vector_store=vector_store,
            embeddings=embeddings,
            bm25_index=bm25_index,
            filter_extractor=filter_extractor,
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
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    main()