# uv run python 03.02.hybrid_search_meta_llm.py
# httpx POST 방식으로 팀 vLLM 서버 호출

# 필요 라이브러리
# uv add langchain-chroma langchain-huggingface kiwipiepy rank-bm25 python-dotenv pydantic httpx

# ============================================================
# LLM 기반 Metadata Filter 생성 원리
# ============================================================
#
# 1. 프로그램 시작 시 ChromaDB에 저장된 실제 metadata 목록을 한 번 로드합니다.
#    - brand_name
#    - product_name
#    - category_names
#    - analysis_category_name
#    - attribute_name
#    - sentiment
#
# 2. 사용자 질문과 위 metadata 후보 목록을 LLM 프롬프트에 함께 전달합니다.
#
# 3. LLM은 후보 목록 안에서만 다음 값을 선택하여 JSON으로 반환합니다.
#    - 브랜드
#    - 상품명 핵심 표현
#    - 상품 카테고리
#    - 분석 카테고리
#    - 속성
#    - 감성 조건
#
# 4. Pydantic이 LLM 응답의 JSON 구조와 자료형을 검증합니다.
#
# 5. 코드가 LLM 응답을 실제 ChromaDB metadata 값과 다시 검증합니다.
#    후보 목록에 없는 값이나 잘못된 값은 최종 필터에서 제외합니다.
#
# 6. 검증된 Metadata Filter를 Chroma 벡터 검색과 BM25 검색에 동일하게 적용합니다.
#
# 7. Kiwi는 metadata 추출에는 사용하지 않고 BM25 검색용 키워드 추출에만 사용합니다.
#
# 8. sentiment는 새로 리뷰 감성분석을 수행하는 것이 아닙니다.
#    사용자가 긍정/부정 리뷰를 요구했을 때 이미 저장된 sentiment metadata를 필터링합니다.
#
# 9. 터미널에는 브랜드 / 상품명 / 상품 카테고리 / 분석 카테고리 / 속성 / 감성을
#    항상 모두 표시하며, 적용되지 않은 항목은 '(없음)'으로 출력합니다.

"""
Oliview 하이브리드 검색
---------------------------------------------------------------
전체 흐름
---------------------------------------------------------------
사용자 질문
    │
    ▼
LLM + Chroma metadata 검증
(브랜드 / 상품명 / 상품 카테고리 / 분석 카테고리 / 속성 / 감성 조건 선택 및 검증)
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
uv add langchain-chroma langchain-huggingface kiwipiepy rank-bm25 python-dotenv pydantic httpx

-------------------------------------------------------------
질문 입력 예시
-------------------------------------------------------------
질문: 식물나라의 보습력이 좋은 토너 추천해줘

Metadata Filter:
- brand_name = 식물나라
- product_name = 특정 상품명이 질문에 있을 때 실제 전체 상품명
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

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Literal

from dotenv import load_dotenv
from kiwipiepy import Kiwi
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi
from pydantic import BaseModel, Field, field_validator

from llm_common import (
    check_server_health,
    load_sample_config,
    get_httpx_client,
    clean_think_tags,
    NO_THINK_SYSTEM_PROMPT,
)


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
PRODUCT_NAME_FILTER_FIELD = "product_name"
CATEGORY_FILTER_FIELD = "category_names"
SENTIMENT_FILTER_FIELD = "sentiment"

# 팀 vLLM 서버 설정(config.json 사용)
LLM_CONFIG = load_sample_config()
SERVER_HOST = LLM_CONFIG["server_host"]
MAIN_PORT = LLM_CONFIG["main_port"]
META_FILTER_MODEL = LLM_CONFIG["default_model"]
TARGET_URL = f"{SERVER_HOST}:{MAIN_PORT}/v1/chat/completions"
META_FILTER_MAX_OUTPUT_TOKENS = LLM_CONFIG.get("no_think_max_tokens", 512)
LLM_HTTP_TIMEOUT = 180.0

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
        실제 ChromaDB metadata 기준으로 검증된 최종 필터 값입니다.
        예: {"brand_name": ["식물나라"], "attribute_name": ["보습"]}

    chroma_where:
        Chroma collection.query(where=...)에 전달할 최종 where 조건입니다.
    """

    field_values: dict[str, list[str]] = field(default_factory=dict)
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
        brand_name = ["식물나라"]
        attribute_name = ["보습", "지속력"]

        → 식물나라이면서 속성이 보습 또는 지속력인 문장
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
# [9] LLM 구조화 출력 자료형
# ============================================================

class LLMMetadataOutput(BaseModel):
    """
    LLM이 ChromaDB의 실제 metadata 후보 목록에서 선택한 결과입니다.

    category_names와 attribute_name은 여러 값이 가능하므로 리스트로 관리합니다.
    다만 소형 LLM이 값이 하나일 때 문자열 하나로 반환할 수 있으므로,
    Pydantic 검증 전에 문자열을 리스트로 자동 변환합니다.
    """

    brand_name: str = Field(
        default="",
        description="ChromaDB에 실제 저장된 브랜드명. 없으면 빈 문자열",
    )

    product_name_term: str = Field(
        default="",
        description=(
            "질문에 특정 상품명이 있을 때 그 상품을 식별하는 핵심 표현. "
            "예: 다이브인 세럼, 블랙 쿠션. 상품명이 없으면 빈 문자열"
        ),
    )

    category_names: list[str] = Field(
        default_factory=list,
        description="ChromaDB에 실제 저장된 상품 카테고리 값 목록",
    )

    analysis_category_name: str = Field(
        default="",
        description=(
            "구체적인 상품 카테고리가 없을 때 사용하는 "
            "ChromaDB의 실제 분석 카테고리명"
        ),
    )

    attribute_name: list[str] = Field(
        default_factory=list,
        description="ChromaDB에 실제 저장된 속성명 목록",
    )

    sentiment: Literal["positive", "negative", "none"] = Field(
        default="none",
        description=(
            "긍정 리뷰 조건은 positive, 부정 리뷰 조건은 negative, "
            "감성 조건이 없으면 none"
        ),
    )

    @field_validator("category_names", "attribute_name", mode="before")
    @classmethod
    def convert_single_value_to_list(cls, value: Any) -> list[str]:
        """
        LLM이 값 하나를 문자열로 반환해도 리스트로 자동 변환합니다.

        예:
            "스킨/토너"
            → ["스킨/토너"]

            ""
            → []

            null
            → []
        """

        if value is None:
            return []

        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []

        if isinstance(value, list):
            return value

        return [str(value).strip()]


# ============================================================
# [17] 질문에서 Metadata Filter 생성
# ============================================================

class MetadataFilterExtractor:
    """
    LLM으로 사용자 질문의 metadata 조건을 해석합니다.

    핵심 원칙:
    1. 프로그램 시작 시 ChromaDB의 브랜드, 상품명, 상품 카테고리,
       분석 카테고리, 속성, 감성 metadata 목록을 한 번 준비합니다.
    2. 질문마다 사용자 질문과 실제 metadata 후보 목록을 LLM에 함께 전달합니다.
    3. LLM은 브랜드·카테고리·속성은 후보 목록에서 선택하고,
       특정 상품명이 있으면 질문에서 상품명 핵심 표현을 추출해 JSON으로 반환합니다.
    4. 질문 원문 표현을 따로 저장하는 중간 후보 필드는 사용하지 않습니다.
    5. Kiwi는 BM25 검색 키워드 추출에만 사용합니다.
    6. LLM 결과를 실제 Chroma metadata 값과 코드에서 다시 검증합니다.
    7. LLM 호출이 실패하면 빈 필터를 반환하여 전체 문장을 검색합니다.
    """

    def __init__(self, bm25_index: ChromaBM25Index):
        self.bm25_index = bm25_index

        if not check_server_health(
            SERVER_HOST,
            MAIN_PORT,
            "vllm_serv 메인 API",
        ):
            raise RuntimeError(
                "LLM 서버 상태 확인에 실패했습니다. "
                "config.json의 server_host/main_port와 서버 실행 상태를 확인해주세요."
            )

        self.model = META_FILTER_MODEL
        self.target_url = TARGET_URL

        self.field_vocabularies: dict[str, list[str]] = {
            key: sorted(
                bm25_index.metadata_values(key),
                key=lambda value: len(normalize_for_match(value)),
                reverse=True,
            )
            for key in EXACT_FILTER_FIELDS
        }

        # product_name은 사용자가 전체 상품명을 그대로 입력하지 않는 경우가 많으므로
        # 실제 상품명 목록은 메모리에 보관하고, LLM이 뽑은 핵심 표현과 Python에서 포함 매칭합니다.
        self.product_name_values = sorted(
            bm25_index.metadata_values(PRODUCT_NAME_FILTER_FIELD),
            key=lambda value: len(normalize_for_match(value)),
            reverse=True,
        )

        self.category_full_values = sorted(
            bm25_index.metadata_values(CATEGORY_FILTER_FIELD),
            key=lambda value: len(normalize_for_match(value)),
            reverse=True,
        )
        self.category_token_to_full_values = self._build_category_token_map()
        self.sentiment_values = bm25_index.metadata_values(
            SENTIMENT_FILTER_FIELD
        )

        self.normalized_value_maps: dict[str, dict[str, str]] = {
            key: {
                normalize_for_match(value): value
                for value in values
            }
            for key, values in self.field_vocabularies.items()
        }

        # category_names는 별도 필드이므로 실제 전체 저장값 검증 맵을 따로 만듭니다.
        self.category_full_normalized_map: dict[str, str] = {
            normalize_for_match(value): value
            for value in self.category_full_values
        }

        self.category_normalized_token_map: dict[str, str] = {
            normalize_for_match(token): token
            for token in self.category_token_to_full_values
        }

        print("\n" + "=" * 90)
        print("[LLM Metadata Filter 준비]")
        print("=" * 90)
        print(f"LLM 서버          : {self.target_url}")
        print(f"LLM 모델          : {self.model}")
        print(
            f"브랜드 값         : "
            f"{len(self.field_vocabularies.get('brand_name', [])):,}개"
        )
        print(
            f"분석 카테고리 값  : "
            f"{len(self.field_vocabularies.get('analysis_category_name', [])):,}개"
        )
        print(
            f"속성 값           : "
            f"{len(self.field_vocabularies.get('attribute_name', [])):,}개"
        )
        print(f"상품명 값         : {len(self.product_name_values):,}개")
        print(f"상품 카테고리 값  : {len(self.category_full_values):,}개")
        print(f"감성 값           : {len(self.sentiment_values):,}개")
        print("[INFO] 위 metadata 목록은 질문마다 LLM 프롬프트에 함께 제공됩니다.")


        print("=" * 90)

    def _build_category_token_map(self) -> dict[str, set[str]]:
        """
        category_names가 쉼표로 연결된 전체 경로일 때 각 카테고리명을
        실제 전체 metadata 값으로 연결합니다.

        LLM은 원칙적으로 전체 category_names 값을 반환하지만,
        예외적으로 하위 카테고리 토큰만 반환한 경우의 안전한 보정에도 사용합니다.
        """

        token_map: dict[str, set[str]] = {}

        for full_value in self.category_full_values:
            for part in full_value.split(","):
                cleaned_part = str(part).strip()
                normalized_part = normalize_for_match(cleaned_part)

                if len(normalized_part) < 2:
                    continue

                token_map.setdefault(cleaned_part, set()).add(full_value)

        return token_map

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
                conditions.append({key: {"$eq": cleaned_values[0]}})
            else:
                conditions.append({key: {"$in": cleaned_values}})

        if not conditions:
            return None

        if len(conditions) == 1:
            return conditions[0]

        return {"$and": conditions}

    @staticmethod
    def _compact_list(values: list[str]) -> str:
        return json.dumps(values, ensure_ascii=False)

    def _metadata_prompt(self, query: str) -> str:
        """
        사용자 질문과 ChromaDB에 실제 저장된 metadata 후보 목록을
        LLM에 함께 전달하기 위한 프롬프트를 생성합니다.

        LLM은 자유롭게 값을 생성하지 않고 실제 후보 목록에서
        최종 필터에 사용할 metadata 값을 직접 선택합니다.
        """

        brands = self.field_vocabularies.get("brand_name", [])
        analysis_categories = self.field_vocabularies.get(
            "analysis_category_name",
            [],
        )
        attributes = self.field_vocabularies.get("attribute_name", [])
        sentiments = self.sentiment_values

        return f"""
사용자 질문을 Oliview 검색용 metadata 조건으로 분석하세요.

[사용자 질문]
{query}

[중요 원칙]
- 아래 후보 목록은 현재 ChromaDB에 실제 저장된 metadata 값입니다.
- brand_name, category_names, analysis_category_name, attribute_name은
  반드시 제공된 후보 목록의 값을 글자까지 그대로 선택하세요.
- product_name_term은 예외적으로 질문에서 특정 상품을 식별하는 핵심 표현만 추출하세요.
  실제 전체 상품명은 코드가 ChromaDB 상품명 목록에서 포함 관계로 찾아냅니다.
- 후보에 없는 값을 새로 만들거나 유사 표현을 그대로 반환하지 마세요.
- 사용자 표현이 후보와 달라도 의미가 같으면 후보의 실제 저장값을 선택하세요.
- 예: 사용자가 '썬크림'이라고 말하고 실제 category_names 후보가
  '선케어, 선크림'이라면 category_names에 '선케어, 선크림'을 반환하세요.
- 질문에 해당 조건이 없으면 빈 문자열 또는 빈 배열을 반환하세요.
- 질문 원문 표현을 별도 필드로 반환하지 말고, 실제 metadata 값만 반환하세요.

[필드별 반환 규칙]
1. brand_name
   - 브랜드 후보에서 질문에 명시된 브랜드 하나를 선택합니다.
   - 없으면 빈 문자열입니다.

2. product_name_term

- 사용자가 특정 상품을 언급한 경우 상품을 식별할 수 있는 핵심 상품명을 추출합니다.
- 상품명 전체를 정확하게 생성할 필요는 없으며, 실제 상품명에 포함될 가능성이 높은 핵심 명칭만 반환합니다.
- 브랜드명은 제외합니다.
- 용량, 수량, 기획, 단품, 리필, 더블기획 등 판매 구성 정보는 제외합니다.
- 단순한 상품 종류(토너, 세럼, 크림, 쿠션, 앰플 등)만 언급된 경우에는 빈 문자열("")을 반환합니다.
- 상품을 식별할 수 있는 고유 명칭(Line name)이 있으면 반드시 추출합니다.
- 여러 단어를 함께 사용해야 특정 상품을 식별할 수 있는 경우에는 함께 반환합니다.
- 한 단어만으로도 특정 상품을 식별할 수 있는 경우에는 해당 단어만 반환합니다.
- product_name_term은 이후 Python에서 실제 상품명과 포함 매칭하여 검색에 사용됩니다.
- - 상품을 식별할 수 있는 고유 명칭이 질문에 포함되어 있다면, 반드시 product_name_term을 추출합니다.

예시)

"토너 추천"
→ ""

"세럼 추천"
→ ""

"식물나라 유채꿀 촉촉 멀티오일 수분감"
→ "유채꿀 촉촉 멀티오일"

"식물나라 뽀얀쌀 클렌징폼 향"
→ "뽀얀쌀"

"헤라 블랙쿠션 지속력"
→ "블랙쿠션"

"토리든 다이브인 세럼"
→ "다이브인 세럼"

"차앤박 아쿠아 수딩 크림"
→ "아쿠아 수딩 크림"

"라운드랩 독도 토너"
→ "독도"

"브링그린 티트리 시카 수딩 세럼"
→ "티트리 시카 수딩 세럼"

"메디힐 마데카소사이드 에센스"
→ "마데카소사이드 에센스"

3. category_names
   - 상품 카테고리 전체 metadata 후보에서 가장 구체적으로 맞는 실제 저장값을 선택합니다.
   - 여러 종류를 동시에 요구하면 여러 값을 반환할 수 있습니다.
   - category_names가 하나 이상이면 analysis_category_name은 빈 문자열이어야 합니다.

4. analysis_category_name
   - 구체적인 category_names를 선택할 수 없을 때만 사용합니다.
   - 분석 카테고리 후보에서 하나를 선택하며, category_names가 비어 있을 때만 사용합니다.

5. attribute_name
   - 아래 속성 후보 중 사용자가 요구한 속성을 선택합니다.
   - 여러 속성을 요구하면 여러 개를 반환합니다.
   - 질문 표현과 가장 직접적으로 대응하는 구체적인 속성을 선택합니다.
   - 넓은 속성인 '기능/효과'보다 구체적인 속성을 우선합니다.

   [속성 정규화 예시]
   - 보습, 보습력, 촉촉함, 수분, 건조하지 않은 → 수분감
   - 발림, 잘 발리는, 부드럽게 펴지는 → 발림성
   - 오래가는, 유지력, 지속되는 → 지속력
   - 커버, 잡티 가림, 가려지는 → 커버력
   - 향, 냄새, 향기 → 향

6. sentiment
   - 부정 리뷰, 단점, 불만, 최악, 별로인 점처럼 부정 의견만 요구하면 negative입니다.
   - 긍정 리뷰, 장점, 만족 의견처럼 긍정 의견만 요구하면 positive입니다.
   - 단순한 '좋은 제품', '추천', '괜찮은 제품'은 긍정 리뷰만 요구하는 것이 아니므로 none입니다.

[브랜드 후보 - 실제 brand_name]
{self._compact_list(brands)}

[상품 카테고리 후보 - 실제 category_names 전체 저장값]
{self._compact_list(self.category_full_values)}

[분석 카테고리 후보 - 실제 analysis_category_name]
{self._compact_list(analysis_categories)}

[속성 후보 - 실제 attribute_name]
{self._compact_list(attributes)}

[감성 metadata 후보 - 실제 sentiment 저장값 확인용]
{self._compact_list(sentiments)}
""".strip()

    def _call_llm(self, query: str) -> dict[str, Any]:
        """httpx로 팀 vLLM 서버를 호출하고 Pydantic으로 JSON을 검증합니다."""

        schema_str = json.dumps(
            LLMMetadataOutput.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{NO_THINK_SYSTEM_PROMPT}\n"
                        "당신은 한국어 화장품 검색 질의를 구조화하는 "
                        "metadata filter 추출기입니다.\n"
                        "반드시 ChromaDB에서 제공한 실제 후보 목록의 값을 "
                        "그대로 선택하고 JSON 객체만 반환하세요. "
                        "후보에 없는 metadata 값을 생성하지 마세요.\n"
                        f"JSON Schema:\n{schema_str}"
                    ),
                },
                {
                    "role": "user",
                    "content": self._metadata_prompt(query),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": META_FILTER_MAX_OUTPUT_TOKENS,
        }

        with get_httpx_client(timeout=LLM_HTTP_TIMEOUT) as client:
            response = client.post(
                self.target_url,
                json=payload,
                headers={"Connection": "close"},
            )
            response.raise_for_status()
            response_data = response.json()

        try:
            raw_content = (
                response_data["choices"][0]["message"]["content"]
                or ""
            )

            print("\n[DEBUG] LLM 원본 응답")
            print(raw_content)
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                "LLM 서버 응답에서 choices[0].message.content를 찾지 못했습니다."
            ) from error

        clean_content = clean_think_tags(
            str(raw_content),
            show_think=False,
        ).strip()

        if not clean_content:
            raise RuntimeError("LLM이 metadata 분석 결과를 반환하지 않았습니다.")

        parsed_model = LLMMetadataOutput.model_validate_json(clean_content)
        return parsed_model.model_dump()

    def _validate_exact_values(
        self,
        key: str,
        raw_values: list[str],
    ) -> list[str]:
        """LLM 결과가 ChromaDB의 실제 metadata 값과 정확히 일치하는지 검증합니다."""

        normalized_map = self.normalized_value_maps.get(key, {})
        validated: list[str] = []

        for raw_value in raw_values:
            normalized = normalize_for_match(raw_value)
            actual_value = normalized_map.get(normalized)

            if actual_value:
                validated.append(actual_value)

        return unique_nonempty(validated)

    def _validate_brand(self, raw_brand: str, query: str) -> list[str]:
        """
        LLM이 선택한 브랜드가 실제 Chroma 브랜드 값과 일치하는지 검증합니다.
        정확히 일치하지 않으면 질문에 실제 브랜드명이 포함됐는지 한 번 더 확인합니다.
        """

        exact = self._validate_exact_values("brand_name", [raw_brand])
        if exact:
            return exact[:1]

        query_normalized = normalize_for_match(query)
        matches = [
            value
            for value in self.field_vocabularies.get("brand_name", [])
            if len(normalize_for_match(value)) >= 2
            and normalize_for_match(value) in query_normalized
        ]

        return matches[:1]

    def _match_product_names(
        self,
        product_name_term: str,
    ) -> list[str]:
        """
        LLM이 질문에서 추출한 상품명 핵심 표현을 이용해
        ChromaDB에 저장된 실제 전체 product_name 값을 찾습니다.

        Chroma 문자열 metadata에 부분 문자열 조건을 직접 전달하지 않습니다.
        대신 Python에서 먼저 포함 관계를 검사한 뒤, 실제 전체 상품명을
        최종 field_values에 넣어 Chroma에서는 $eq 또는 $in으로 필터링합니다.

        예:
            product_name_term = "다이브인 세럼"
            실제 상품명 = "토리든 다이브인 저분자 히알루론산 세럼 50ml"

        핵심 표현이 여러 단어라면 모든 단어가 실제 상품명에 포함되어야 합니다.
        따라서 중간에 다른 단어가 들어간 긴 상품명도 찾을 수 있습니다.
        """

        cleaned_term = str(product_name_term or "").strip()
        normalized_term = normalize_for_match(cleaned_term)

        if len(normalized_term) < 2:
            return []

        # 공백 기준 핵심 단어를 모두 포함하는 상품명을 찾습니다.
        term_tokens = [
            normalize_for_match(token)
            for token in cleaned_term.split()
            if normalize_for_match(token)
        ]

        matched_values: list[str] = []

        for product_name in self.product_name_values:
            normalized_product = normalize_for_match(product_name)

            if term_tokens:
                is_match = all(token in normalized_product for token in term_tokens)
            else:
                is_match = normalized_term in normalized_product

            if is_match:
                matched_values.append(product_name)

        return unique_nonempty(matched_values)

    def _validate_categories(
        self,
        raw_values: list[str],
    ) -> list[str]:
        """
        LLM이 반환한 category_names 전체 저장값을 실제 ChromaDB 값과 검증합니다.

        원칙적으로 정확히 일치하는 전체 저장값만 사용합니다.
        다만 LLM이 예외적으로 '선크림'처럼 하위 토큰만 반환한 경우에는
        기존 alias와 category token map을 이용해 실제 전체 저장값으로 보정합니다.
        """

        validated: set[str] = set()

        for raw_value in raw_values:
            original = str(raw_value or "").strip()
            normalized = normalize_for_match(original)

            if not normalized:
                continue

            # 1) 실제 category_names 전체 값과 정확히 일치
            exact_full_value = self.category_full_normalized_map.get(normalized)
            if exact_full_value:
                validated.add(exact_full_value)
                continue

            # 2) 하위 카테고리 토큰 또는 별칭이 반환된 경우 안전 보정
            canonical = CATEGORY_ALIASES.get(normalized, original)
            canonical_normalized = normalize_for_match(canonical)
            actual_token = self.category_normalized_token_map.get(
                canonical_normalized
            )

            if actual_token:
                validated.update(
                    self.category_token_to_full_values.get(actual_token, set())
                )

        return sorted(validated)

    def _validate_sentiment(self, raw_sentiment: str) -> list[str]:
        """positive/negative 의미를 실제 ChromaDB sentiment 저장값으로 변환합니다."""

        target = str(raw_sentiment or "").strip().lower()
        if target not in {"positive", "negative"}:
            return []

        aliases = {
            "positive": ("긍정", "positive", "pos"),
            "negative": ("부정", "negative", "neg"),
        }

        return [
            value
            for value in self.sentiment_values
            if any(
                alias in normalize_for_match(value)
                for alias in aliases[target]
            )
        ]

    def extract(self, query: str) -> MetadataFilterResult:
        cleaned_query = query.strip()
        if not cleaned_query:
            return MetadataFilterResult()

        try:
            llm_result = self._call_llm(cleaned_query)
            print(
                "[INFO] LLM metadata 선택 결과: "
                + json.dumps(llm_result, ensure_ascii=False)
            )
        except Exception as error:
            print(f"[WARNING] LLM Metadata Filter 추출 실패: {error}")
            print("[WARNING] 안전을 위해 metadata 필터 없이 검색합니다.")
            return MetadataFilterResult()

        field_values: dict[str, list[str]] = {}

        brand_values = self._validate_brand(
            str(llm_result.get("brand_name") or ""),
            cleaned_query,
        )
        if brand_values:
            field_values["brand_name"] = brand_values

        # 특정 상품명이 질문에 있으면 핵심 표현으로 실제 전체 상품명을 찾아 필터에 추가합니다.
        product_name_values = self._match_product_names(
            str(llm_result.get("product_name_term") or "")
        )
        if product_name_values:
            field_values[PRODUCT_NAME_FILTER_FIELD] = product_name_values

        category_values = self._validate_categories(
            list(llm_result.get("category_names") or [])
        )
        if category_values:
            field_values[CATEGORY_FILTER_FIELD] = category_values

        # 구체적인 상품 카테고리가 없을 때만 분석 카테고리를 사용합니다.
        if not category_values:
            analysis_values = self._validate_exact_values(
                "analysis_category_name",
                [str(llm_result.get("analysis_category_name") or "")],
            )
            if analysis_values:
                field_values["analysis_category_name"] = analysis_values[:1]

        attribute_values = self._validate_exact_values(
            "attribute_name",
            list(llm_result.get("attribute_name") or []),
        )
        if attribute_values:
            field_values["attribute_name"] = attribute_values

        sentiment_values = self._validate_sentiment(
            str(llm_result.get("sentiment") or "none")
        )
        if sentiment_values:
            field_values[SENTIMENT_FILTER_FIELD] = sentiment_values

        return MetadataFilterResult(
            field_values=field_values,
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

    # 2. LLM으로 질문을 분석하고 실제 Chroma metadata 값으로 검증하여 Filter 생성
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
    """
    최종 Metadata Filter를 여섯 개 필드 모두 출력합니다.

    필터가 적용되지 않은 필드도 생략하지 않고 '(없음)'으로 표시하여,
    LLM이 어떤 조건을 선택했고 어떤 조건은 선택하지 않았는지 한눈에 확인할 수 있습니다.
    """

    print("\n" + "-" * 100)
    print("[Metadata Filter]")
    print("-" * 100)

    field_order = (
        ("brand_name", "브랜드"),
        ("product_name", "상품명"),
        ("category_names", "상품 카테고리"),
        ("analysis_category_name", "분석 카테고리"),
        ("attribute_name", "속성"),
        ("sentiment", "감성"),
    )

    for key, label in field_order:
        values = metadata_filter.field_values.get(key, [])

        if not values:
            print(f"{label:<15}: (없음)")
            continue

        if key in {"product_name", "category_names"}:
            print(f"{label:<15}:")
            for value in values:
                print(f"{'':<17}- {value}")
        else:
            print(f"{label:<15}: {', '.join(values)}")

    if not metadata_filter.is_active:
        print("-" * 100)
        print("질문에서 적용할 metadata 조건을 찾지 못해 전체 문장을 검색합니다.")

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
    print("예시 질문: 식물나라의 보습력이 좋은 토너 추천해줘")
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

        # BM25 인덱스가 보유한 실제 Chroma metadata 목록을 LLM 프롬프트 후보 및 결과 검증에 사용합니다.
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