# uv run python 03.03.hybrid_search_meta_llm_python_name.py
# httpx POST 방식으로 팀 vLLM 서버 호출

# 필요 라이브러리
# uv add langchain-chroma langchain-huggingface kiwipiepy rank-bm25 python-dotenv pydantic httpx

# ============================================================
# 핵심
# ============================================================
# 사용자 질문에서 
# ChromaDB의 실제 metadata를 기준으로 질문의 검색 조건을 만들고,
# 같은조건 안에서는 Chroma Vector Search와 Kiwi기반 BM25 Search을 동시에 수행하고, 
# 두 결과를 RRF로 합치는 하이브리드 검색코드
#
# ============================================================
# LLM + Python 기반 Metadata Filter 생성 원리
# ============================================================
#
# 1.프로그램 시작 시 ChromaDB의 전체 리뷰 문장과 metadata를 한 번 로드하고,
#   검색 조건 생성에 필요한 metadata의 실제 고유값 목록을 준비합니다
#    - brand_name
#    - product_name
#    - category_names
#    - analysis_category_name
#    - attribute_name
#    - sentiment
#
# 2. Metadata Filter 추출 방식에 따라 사용자 질문에서
#    다음 조건을 추출합니다.
#
#    USE_LLM_METADATA_FILTER = True
#    → LLM이 구조화된 JSON으로 추출
#
#    USE_LLM_METADATA_FILTER = False
#    → Python 규칙으로 추출
#
#    - 브랜드
#    - 상품 카테고리
#    - 분석 카테고리
#    - 속성
#    - 감성 조건
#
# 3. 상품명은 LLM이 추출하지 않습니다.
#    Python이 사용자 질문의 단어와 ChromaDB의 실제 product_name을 비교하여 찾습니다.
#    - 1) 질문토큰 생성
#    - 2) 불필요한 토큰 제거
#    - 3) 직접 부분 문자열 매칭
#    - 4) 실패하면 점수기반 매칭
#
# 4. LLM Metadata Filter를 사용하는 경우,
#    Pydantic이 LLM 응답의 JSON 구조와 자료형을 검증합니다.
#
# 5. 추출된 metadata 조건과 Python 상품명 매칭 결과를
#    ChromaDB에 실제 저장된 metadata 값과 다시 검증합니다.
#
# 6. 검증된 Metadata Filter를 
#    Chroma 벡터 검색과 BM25 검색에 동일하게 적용합니다.
#
# 7. Kiwi는 두 곳에서 사용합니다.
#    - BM25 검색용 질문/문서 키워드 추출          -> extract_query_keywords(), tokenize_document()
#    - Python 상품명 매칭을 위한 보조 토큰 추출   -> _raw_query_tokens()
#
# 8. sentiment는 새 감성분석을 수행하는 것이 아니라,
#    이미 ChromaDB에 저장된 sentiment metadata를 필터링합니다.
#
# 9. 터미널에는 브랜드 / 상품명 / 상품 카테고리 /
#    분석 카테고리 / 속성 / 감성을 항상 모두 표시합니다.
#    적용되지 않은 항목은 '(없음)'으로 출력합니다.

"""
Oliview 하이브리드 검색
---------------------------------------------------------------
전체 흐름
---------------------------------------------------------------
프로그램 실행
    ↓
프로젝트 ROOT 경로 탐색
    ↓
.env / config.json 설정 로드
    ↓
BGE-M3 임베딩 모델 로드
    ↓
ChromaDB 연결
    ↓
ChromaDB의 전체 리뷰 문장 로드
    ↓
Kiwi로 전체 리뷰 문장 토큰화
    ↓
BM25 인덱스 생성
    ↓
Chroma metadata 실제 값 목록 준비
    ↓
사용자 질문 입력
    ↓
Kiwi로 BM25 검색용 질문 키워드 추출
    ↓
Metadata Filter 생성
    ├─ USE_LLM_METADATA_FILTER=True
    │      ↓
    │   LLM으로
    │   브랜드 / 상품 카테고리 / 분석 카테고리 /
    │   속성 / 감성 추출
    │
    └─ USE_LLM_METADATA_FILTER=False
           ↓
        Python 규칙으로 위 조건 추출
    ↓
실제 Chroma metadata 값과 검증
    ↓
Python으로 질문의 상품명 별도 매칭
    ↓
최종 Metadata Filter 생성
    ↓
           같은 Filter 적용
          ┌──────┴──────┐
          ↓             ↓
     Vector Search    BM25 Search
     질문 원문        Kiwi 키워드
          │             │
          └──────┬──────┘
                 ↓
                RRF
                 ↓
              Top-K 반환
                 ↓
          터미널 결과 출력

-------------------------------------------------------------
질문 입력 예시
-------------------------------------------------------------
질문: 식물나라 어린 녹차 클렌징 사용감 

Metadata Filter:
- brand_name = 식물나라
- product_name = Python이 질문의 고유 단어와 ChromaDB의 실제 상품명을 비교하여 검색
- category_names = 질문의 상품 종류 표현을 ChromaDB의 실제 카테고리 값으로 검증
- analysis_category_name = 클렌징
- attribute_name = 사용감
- sentiment = 조건 없음 → 긍정·부정 모두 검색
-------------------------------------------------------------
RRF 점수
-------------------------------------------------------------
RRF 점수 = 1 / (60 + Chroma 순위)
         + 1 / (60 + BM25 순위)
"""

import json  # JSON 생성·파싱 -> LLM 결과, Schema, 디버그 출력 등에 사용
import os    # 파일경로, 환경변수 확인에 사용
import re    # 정규표현식 -> 질문정리, 상품명 토큰 추출, 조사제거
import sys   # LLM 결과, Schema, 디버그 출력 등에 사용
import pickle
from pathlib import Path
from dataclasses import dataclass, field  # 검색결과와 Metadata Filter를 객체형태로 관리
from typing import Any, Literal           # 타입 힌트
                                            # Any = 어떤 타입도 가능
                                            # Literal["positive", "negative", "none"] = 이 세 문자열만 허용.

from dotenv import load_dotenv
from kiwipiepy import Kiwi
from langchain_chroma import Chroma  # LangChain에서 ChromaDB를 사용하기 위한 Chroma 클래스
                                     # 저장된 리뷰문장과 임베딩 벡터를 불러와 Vector Search를 수행할 때 사용
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi      # 키워드 기반 검색 알고리즘인 BM25의 BM25Okapi 클래스
from pydantic import BaseModel, Field, field_validator # 데이터 구조와 입력값을 정의·검증하기 위한 Pydantic 기능
# BaseModel → 데이터 구조를 정의하는 기본 클래스
# Field → 각 필드의 기본값, 설명, 조건 등을 설정
# field_validator → 특정 필드의 값이 올바른지 검사하거나 전처리

# 같은 프로젝트 안에 있는 llm_common.py에서 여러 함수와 상수를 가져옴
from llm_common import (
    check_server_health,    # LLM 서버가 정상적으로 실행 중인지 확인 
    load_sample_config,     # LLM 사용에 필요한 설정값 불러옴(서버URL, 모델관련 설정)
    get_httpx_client,       # LLM 서버에 HTTP 요청을 보내기 위한 httpx 클라이언트를 생성하거나 가져오는 함수
    clean_think_tags,       # LLM 응답에 포함될 수 있는 <think>...</think> 같은 내부 추론 태그를 제거하는 함수
    NO_THINK_SYSTEM_PROMPT, # LLM이 불필요한 추론 과정 등을 출력하지 않도록 하기 위한 시스템 프롬프트 상수
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

# Python 모듈 검색경로에 ROOT가 없다면
# 맨 앞에 추가함
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from common.utils import get_bge_m3_device

# ROOT의 .env 파일을 읽음
load_dotenv(os.path.join(ROOT_DIR, ".env"))


# ============================================================
# Metadata Filter 추출 방식
# ============================================================

# .env에서 값을 가져옴 -> 없으면 기본값은 "true"
  # USE_LLM_METADATA_FILTER = True    → LLM이 구조화된 JSON으로 추출
  # USE_LLM_METADATA_FILTER = False   → Python 규칙으로 추출

USE_LLM_METADATA_FILTER = (
    os.getenv("USE_LLM_METADATA_FILTER", "true")
    .strip()  # 앞뒤 공백 제거
    .lower()  # 소문자로 변환
    in {"true", "1", "yes", "y", "on"} # 이 값 중 하나이면 True
)

# ============================================================
# [2] 기본 설정
# ============================================================

# 임베딩 모델 경로
# LOCAL_MODEL_PATH = 프로젝트 폴더/models/embeddings/bge-m3
LOCAL_MODEL_PATH = os.path.join(
    ROOT_DIR,
    "models",
    "embeddings",
    "bge-m3",
)

# ChromaDB 저장 경로
# CHROMA_DB_PATH = 프로젝트폴더/chroma_db_oliview
CHROMA_DB_PATH = os.path.join(
    ROOT_DIR,
    "chroma_db_oliview",
)

# ChromaDB 내부 컬렉션명
# oliview_review_sentences 컬렉션 -> 임베딩된 리뷰 문장 데이터가 저장되어 있음
COLLECTION_NAME = "oliview_review_sentences"

# Vector 최대후보 : 20개
# BM25   최대 후보: 20개
DEFAULT_CANDIDATE_K = 20

# RRF 결합 후 최종 후보 : 5개
DEFAULT_FINAL_K = 5

# RRF공식에서 사용하는 상수
# 일반적으로 60을 사용
RRF_K = 60

# 임베딩 계산 배치 크기
EMBEDDING_BATCH_SIZE = 16

# 자동 Metadata Filter에 사용할 필드
# 실제값과 정확하게 검증하는 대상
EXACT_FILTER_FIELDS = (
    "brand_name",
    "analysis_category_name",
    "attribute_name",
)

# 상품명, 카테고리, 감성은 따로 관리
# category_names는 쉼표로 여러 카테고리가 저장될 수 있으므로
# 질문에서 하위 카테고리 단어를 찾은 뒤 실제 전체 metadata 값의 $in으로 변환합니다.
PRODUCT_NAME_FILTER_FIELD = "product_name"
CATEGORY_FILTER_FIELD = "category_names"
SENTIMENT_FILTER_FIELD = "sentiment"

# 팀 vLLM 서버 설정(config.json 사용)
LLM_CONFIG = load_sample_config()        # config.json 파일의 LLM 서버 설정을 불러옴
SERVER_HOST = LLM_CONFIG["server_host"]  # 설정에서 LLM 서버 주소(IP/호스트)를 가져옴
MAIN_PORT = LLM_CONFIG["main_port"]      # LLM 서버의 port 번호 가져옴
META_FILTER_MODEL = LLM_CONFIG["default_model"]  # 서버에서 사용할 기본 LLM 모델명 가져옴
TARGET_URL = f"{SERVER_HOST}:{MAIN_PORT}/v1/chat/completions"  # 서버주소 + port를 합쳐서 LLM에게 질문을 보낼 API 주소를 만듬
META_FILTER_MAX_OUTPUT_TOKENS = LLM_CONFIG.get("no_think_max_tokens", 512) # 메타데이터 필터링 LLM이 최대 몇토큰까지 출력할지 가져옴
                                                                           # config.json에 no_think_max_tokens가 없으면 기본값 512를 사용
LLM_HTTP_TIMEOUT = 180.0 # LLM 서버에 요청한 뒤 최대 180초(3분)까지 응답을 기다림

# ============================================================
# Python 메타데이터 필터링 - 카테고리 매칭 설정
# ============================================================
# Python 메타데이터 필터링용 카테고리 동의어 매핑
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
# # Python 메타데이터 필터링 - 상품명 매칭 설정
# ============================================================

# 상품 종류나 검색 의도를 나타내는 일반 단어입니다.
# 이 단어들만 질문에 존재하는 경우에는 특정 상품명으로 판단하지 않습니다.
PRODUCT_GENERIC_TERMS = {
    # 검색 의도
    "추천", "추천해줘", "알려줘", "알려", "어때", "어떻게", "후기",
    "리뷰", "제품", "상품", "좋은", "좋다", "괜찮은", "찾아줘",

    # 상품 종류
    "스킨", "토너", "세럼", "에센스", "앰플", "크림", "로션",
    "에멀전", "미스트", "오일", "멀티오일", "아이크림", "립밤",
    "쿠션", "파운데이션", "파우더", "팩트", "립스틱", "틴트",
    "클렌징", "클렌", "클렌저", "클렌징폼", "폼", "클렌징젤", "젤",
    "클렌징밤", "밤", "클렌징오일", "클렌징워터", "클렌징크림",
    "선크림", "썬크림", "선스틱", "선쿠션", "마스크", "팩","마스카라"
}

# 질문에서 속성 조건으로 사용되지만 상품 고유명으로는 보지 않는 표현입니다.
PRODUCT_ATTRIBUTE_TERMS = {
    "수분", "수분감", "보습", "보습력", "촉촉함",
    "발림", "발림성", "지속", "지속력", "커버", "커버력",
    "밀착", "밀착력", "향", "냄새", "향기", "사용감",
    "세정", "세정력", "자극", "자극도", "진정", "흡수", "흡수력",
    "기능", "효과", "기능효과",
}

# 감성이나 평가 방향을 나타내므로 상품명 토큰에서 제외합니다.
PRODUCT_SENTIMENT_TERMS = {
    "긍정", "부정", "최악", "최고", "별로", "불만", "단점",
    "장점", "만족", "좋음", "나쁨", "좋아", "안좋아",

    "장단점",
    "장점과",
    "단점과",
    "긍정과",
    "부정과",
}

PRODUCT_QUERY_STOP_TERMS = {
    # 요청 표현
    "알려줘",
    "알려주세요",
    "알려",
    "알리",
    "말해줘",
    "말해주세요",
    "보여줘",
    "보여주세요",

    # 분석 요청 표현
    "분석",
    "분석해",
    "분석해주세요",
    "요약",
    "요약해",
    "요약해주세요",

    # 소비자 의견 표현
    "소비자",
    "의견",
    "평가",
    "소비자의견",
    "긍정의견",
    "부정의견",
    "긍정평가",
    "부정평가",

    # 장점·단점·개선 관련 표현
    "단점알려줘",
    "장점알려줘",
    "개선",
    "개선점",
    "개선할점",
    "개선사항",
    "아쉬운점",
    "문제점",
    "불편한점",
}

# 용량·수량·판매 구성 표현은 실제 상품명 매칭 점수에서 제외합니다.
PRODUCT_SALES_TERMS = {
    "기획", "더블기획", "단품", "리필", "세트", "증정", "한정",
    "택1", "1+1", "2개", "본품",
}


# ============================================================
# [3] 검색 결과 및 Metadata Filter 자료형
# ============================================================

# 1) 검색결과 한 건을 저장하는 상자
@dataclass
class SearchItem:
    document_id: str                      # 리뷰문장 ID
    text: str                             # 리뷰문장
    metadata: dict[str, Any]              # 메타데이터

    vector_rank: int | None = None        # Vector 검색 순위
    vector_distance: float | None = None  # Vector 거리

    bm25_rank: int | None = None          # BM25 순위
    bm25_score: float | None = None       # BM25 점수
    rrf_score: float = 0.0                # 최종 RRF점수

# 2) 사람이 이해하기 쉬운 최종조건
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

    # 필터가 하나라도 있으면 True
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

    # None이면 ""로 -> 문자열 변환 -> 앞뒤 공백 제거 -> 소문자화 
    text = str(value or "").strip().lower()

    # 모든 공백을 제거
    return re.sub(r"\s+", "", text)


def unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()  # 이미 본값
    result: list[str] = []  # 결과

    for value in values:
        cleaned = str(value or "").strip() # 문자열로 변환하고 정리

        if not cleaned or cleaned in seen: # 빈 문자열 또는 중복이면 건너뜀
            continue

        # 처음 나온 유효한 값만 저장
        seen.add(cleaned)
        result.append(cleaned)

    return result


# ============================================================
# [5] Kiwi 형태소 분석기
# ============================================================

# 처음에는 Kiwi가 없음
_KIWI: Kiwi | None = None


def get_kiwi() -> Kiwi:
    global _KIWI

    # 처음 호출할 때 한번만 생성
    # 그 다음에는 기존 _KIWI 재사용
    if _KIWI is None:
        print("[INFO] Kiwi 형태소 분석기 로드 중...")
        _KIWI = Kiwi()
        print("[INFO] Kiwi 형태소 분석기 준비 완료")

    return _KIWI

def extract_keywords(text: str) -> list[str]:
    """
    BM25 검색 및 metadata 조건 탐색에 사용할
    기본 Kiwi 키워드를 추출합니다.
    """

    cleaned_text = str(text or "").strip()

    if not cleaned_text:
        return []

    try:
        kiwi = get_kiwi()
        tokens = kiwi.tokenize(cleaned_text)

        # 허용품사
        allowed_tags = {
            "NNG",  # 일반명사
            "NNP",  # 고유명사
            "SL",   # 외국어
            "SN",   # 숫자
            "VA",   # 형용사
            "VV",   # 동사
            "XR",   # 어근
        }

        keywords: list[str] = []

        for token in tokens:
            if token.tag not in allowed_tags:
                continue

            word = token.form.strip().lower()

            if not word:
                continue

            # 한 글자 명사 노이즈 제거
            # 영문·숫자는 허용
            if len(word) == 1 and token.tag in {"NNG", "NNP"}:
                continue

            keywords.append(word)

        if keywords:
            return keywords

    except Exception as error:
        print(f"[WARNING] Kiwi 키워드 추출 실패: {error}")

    # Kiwi 실패 시 안전한 대체 처리
    return [
        word.lower()
        for word in cleaned_text.split() # 단순 공백 분리사용
        if word.strip()
    ]

def extract_query_keywords(text: str) -> list[str]:
    """
    사용자 질문에서 BM25 검색에 사용할 핵심 키워드를 추출합니다.

    기존 extract_keywords()로 Kiwi 형태소 분석을 수행한 뒤,
    검색에 불필요한 질문 의도·감성 표현을 제거합니다.

    예:
    "헤라 블랙쿠션 파운데이션의 소비자 긍정의견 알려줘"
    → ["헤라", "블랙", "쿠션", "파운데이션"]
    """

    # 1. 기존 Kiwi 키워드 추출
    keywords = extract_keywords(text)

    # 2. 사용자 질문에서 검색에 불필요한 표현
    query_stop_terms = {
        # 질문/분석 표현
        "소비자",
        "의견",
        "평가",
        "분석",

        # 감성/분석 의도
        "긍정",
        "부정",
        "장점",
        "단점",

        # 요청 표현
        "알리",
        "알려",
        "말하",
    }

    # 3. 불용어 제거
    filtered_keywords = [
        keyword
        for keyword in keywords
        if keyword not in query_stop_terms
    ]

    return filtered_keywords


def tokenize_document(text: str) -> list[str]:
    """BM25에 등록할 리뷰 문장도 질문과 같은 방식으로 토큰화합니다."""

    return extract_keywords(text)


# ============================================================
# [6] BGE-M3 임베딩 모델 생성
# ============================================================

# modules.json, modules.json가 모두 있는지 확인
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

    device = get_bge_m3_device()  # CPU/GPU 등의 사용장치를 결정

    print("\n" + "=" * 90)
    print("[BGE-M3 임베딩 모델 로드]")
    print("=" * 90)
    print(f"모델 경로 : {LOCAL_MODEL_PATH}")
    print(f"사용 장치 : {device}")
    print("=" * 90)

    embeddings = HuggingFaceEmbeddings( # 임베딩 모델 생성
        model_name=LOCAL_MODEL_PATH,
        model_kwargs={
            "device": device,
            "local_files_only": True,
        },
        encode_kwargs={
            "normalize_embeddings": True,         # 임베딩을 정규화함
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

        cache_path = Path("/app/chroma_db_oliview/bm25_cache.pkl")
        if not cache_path.parent.exists():
            cache_path = Path("./chroma_db_oliview/bm25_cache.pkl")

        if cache_path.is_file():
            try:
                print(f"[INFO] BM25 디스크 캐시 로드 중: {cache_path}")
                with open(cache_path, "rb") as f:
                    cache_data = pickle.load(f)
                self.document_ids = cache_data["document_ids"]
                self.documents = cache_data["documents"]
                self.metadatas = cache_data["metadatas"]
                self.tokenized_corpus = cache_data["tokenized_corpus"]
                self.bm25 = cache_data["bm25"]
                print(f"[INFO] BM25 캐시 로드 완료 ({len(self.documents):,}개 문장, 즉시 준비 완료)")
                print("=" * 90)
                return
            except Exception as e:
                print(f"[WARNING] BM25 캐시 읽기 실패, 재생성합니다: {e}")

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
            # 문장이 NULL이면 제외
            if document is None: 
                continue

            # 문자열 변환 + 앞뒤 공백제거
            cleaned_document = str(document).strip()

            # 결과가 ""이면 제외 
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

        # 전체리뷰 Kiwi 토큰화
        # 토큰이 하나도 없는 문장은 원문 공백 분리로 보완
        self.tokenized_corpus = [
            tokens if tokens else document.lower().split()
            for tokens, document in zip(
                self.tokenized_corpus,
                self.documents,
            )
        ]

        # BM25 인덱스를 완성함
        self.bm25 = BM25Okapi(self.tokenized_corpus)

        try:
            if cache_path.parent.exists():
                with open(cache_path, "wb") as f:
                    pickle.dump({
                        "document_ids": self.document_ids,
                        "documents": self.documents,
                        "metadatas": self.metadatas,
                        "tokenized_corpus": self.tokenized_corpus,
                        "bm25": self.bm25,
                    }, f, protocol=pickle.HIGHEST_PROTOCOL)
                print(f"[INFO] BM25 캐시 저장 완료: {cache_path}")
        except Exception as e:
            print(f"[WARNING] BM25 캐시 저장 실패: {e}")

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

        # 조건을 하나씩 검사
        for key, allowed_values in field_values.items():
            metadata_value = str(metadata.get(key, "")).strip()

            # 하나라도 불일치 -> 검색후보 탈락
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

    상품명(product_name)은 이 모델에 포함하지 않습니다.
    상품명은 Python이 질문 원문과 실제 ChromaDB product_name 목록을
    직접 비교하여 찾습니다.

    category_names와 attribute_name은 여러 값이 가능하므로 리스트로 관리합니다.
    소형 LLM이 값 하나를 문자열로 반환해도 Pydantic 검증 전에 리스트로 변환합니다.
    """

    brand_name: str = Field(
        default="",
        description="ChromaDB에 실제 저장된 브랜드명. 없으면 빈 문자열",
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
            "스킨/토너" → ["스킨/토너"]
            ""          → []
            null        → []
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
# [9-1] 질문에서 Metadata Filter 생성
# ============================================================

class MetadataFilterExtractor:
    """
    LLM과 Python을 함께 사용하여 사용자 질문의 Metadata Filter를 생성합니다.

    역할 분담
    ------------------------------------------------------------------
    LLM:
        - brand_name
        - category_names
        - analysis_category_name
        - attribute_name
        - sentiment

    Python:
        - product_name
        - 질문 원문의 고유 단어와 실제 ChromaDB product_name을 비교
        - 브랜드와 카테고리 조건을 함께 사용하여 후보 상품을 축소

    상품명 매칭 원리
    ------------------------------------------------------------------
    1. 질문에서 브랜드, 속성, 감성, 검색 의도, 일반 상품 종류를 분리합니다.
    2. 남은 고유 단어를 상품 식별 토큰으로 사용합니다.
    3. 실제 product_name에 해당 토큰이 얼마나 포함되는지 점수를 계산합니다.
    4. 가장 높은 점수의 실제 전체 상품명을 $eq 또는 $in 필터로 사용합니다.

    예:
        질문:
            식물나라 어린 녹차 클렌장 사용감

        LLM:
            brand_name = 식물나라
            category_names = 클렌징폼/젤
            attribute_name = 사용감

        Python 상품명 토큰:
            어린, 녹차

        실제 매칭:
            식물나라 어린녹차 저자극 클렌징밤 100ml
    """

    def __init__(self, bm25_index: ChromaBM25Index):
        self.bm25_index = bm25_index

        self.use_llm_metadata_filter = USE_LLM_METADATA_FILTER
        self.model = META_FILTER_MODEL
        self.target_url = TARGET_URL

        # LLM Metadata Filter를 사용할 때만 서버 상태를 확인합니다.
        if self.use_llm_metadata_filter:
            if not check_server_health(
                SERVER_HOST,
                MAIN_PORT,
                "vllm_serv 메인 API",
            ):
                raise RuntimeError(
                    "LLM 서버 상태 확인에 실패했습니다. "
                    "config.json의 server_host/main_port와 "
                    "서버 실행 상태를 확인해주세요."
                )

        # LLM이 실제 후보 목록에서 선택할 필드입니다.
        self.field_vocabularies: dict[str, list[str]] = {
            key: sorted(
                bm25_index.metadata_values(key),
                key=lambda value: len(normalize_for_match(value)),
                reverse=True,
            )
            for key in EXACT_FILTER_FIELDS
        }

        # 상품명은 LLM 프롬프트에 전달하지 않습니다.
        # Python이 질문과 이 실제 전체 상품명 목록을 직접 비교합니다.
        self.product_name_values = sorted(
            bm25_index.metadata_values(PRODUCT_NAME_FILTER_FIELD),
            key=lambda value: len(normalize_for_match(value)),
            reverse=True,
        )

        # 상품명별 브랜드·카테고리 metadata를 함께 보관합니다.
        # 동일 상품의 리뷰 문장이 여러 개 있어도 set으로 중복을 제거합니다.
        self.product_metadata_map: dict[str, dict[str, set[str]]] = {}

        for metadata in bm25_index.metadatas:
            product_name = str(
                metadata.get(PRODUCT_NAME_FILTER_FIELD, "")
            ).strip()

            if not product_name:
                continue

            record = self.product_metadata_map.setdefault(
                product_name,
                {
                    "brand_name": set(),
                    "category_names": set(),
                },
            )

            brand_name = str(metadata.get("brand_name", "")).strip()
            category_name = str(metadata.get("category_names", "")).strip()

            if brand_name:
                record["brand_name"].add(brand_name)

            if category_name:
                record["category_names"].add(category_name)

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

        self.category_full_normalized_map: dict[str, str] = {
            normalize_for_match(value): value
            for value in self.category_full_values
        }

        self.category_normalized_token_map: dict[str, str] = {
            normalize_for_match(token): token
            for token in self.category_token_to_full_values
        }

        print("\n" + "=" * 90)
        print("[LLM + Python Metadata Filter 준비]")
        print("=" * 90)
        print(f"LLM 서버          : {self.target_url}")
        print(f"LLM 모델          : {self.model}")
        print(
            f"브랜드 값         : "
            f"{len(self.field_vocabularies.get('brand_name', [])):,}개"
        )
        print(f"상품명 값         : {len(self.product_name_values):,}개")
        print(f"상품 카테고리 값  : {len(self.category_full_values):,}개")
        print(
            f"분석 카테고리 값  : "
            f"{len(self.field_vocabularies.get('analysis_category_name', [])):,}개"
        )
        print(
            f"속성 값           : "
            f"{len(self.field_vocabularies.get('attribute_name', [])):,}개"
        )
        print(f"감성 값           : {len(self.sentiment_values):,}개")
        print(
            "[INFO] 상품명을 제외한 metadata 목록은 LLM 프롬프트에 제공됩니다."
        )
        print(
            "[INFO] 상품명은 Python이 질문과 실제 product_name을 직접 비교합니다."
        )
        print("=" * 90)

    def _build_category_token_map(self) -> dict[str, set[str]]:
        """
        쉼표로 연결된 category_names의 각 부분을
        실제 전체 metadata 값으로 연결합니다.
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
        """
        서로 다른 metadata 필드는 AND,
        같은 필드 안의 여러 값은 $in으로 결합합니다.
        """

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
        사용자 질문과 ChromaDB의 실제 metadata 후보 목록을 LLM에 전달합니다.

        상품명은 이 프롬프트에서 추출하지 않습니다.
        Python 상품명 매칭과 역할이 중복되지 않도록 LLM 출력 스키마에서도 제외합니다.
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
- 상품명은 추출하지 마세요. 상품명은 Python 코드가 별도로 찾습니다.
- 후보에 없는 값을 새로 만들거나 질문 표현을 그대로 반환하지 마세요.
- 사용자 표현이 후보와 달라도 의미가 같으면 후보의 실제 저장값을 선택하세요.
- 질문에 해당 조건이 없으면 빈 문자열 또는 빈 배열을 반환하세요.

[필드별 반환 규칙]

1. brand_name
   - 브랜드 후보에서 질문에 명시된 브랜드 하나를 선택합니다.
   - 없으면 빈 문자열입니다.

2. category_names
   - 사용자가 질문에서 상품 종류를 명시한 경우에만 선택합니다.
   - 질문에 직접 나타나지 않은 상품 카테고리를 추측하지 마세요.
   - 브랜드명이나 상품명으로 상품 카테고리를 추측하지 마세요.
   - 실제 상품 카테고리 후보에서 가장 구체적으로 맞는 값을 선택합니다.
   - 여러 상품 종류를 동시에 요구하면 여러 값을 반환할 수 있습니다.
   - category_names가 하나 이상이면 analysis_category_name은 빈 문자열입니다.
   - 예: 썬크림 → 선크림
   - 예: 토너 → 스킨/토너
   - 예: 클렌, 클렌징폼 → 클렌징폼/젤

3. analysis_category_name
   - 구체적인 category_names를 선택할 수 없을 때만 사용합니다.
   - 질문에 직접 나타나지 않은 분석 카테고리를 추측하지 마세요.
   - category_names가 비어 있을 때만 분석 카테고리 후보 중 하나를 선택합니다.

4. attribute_name
   - 속성 후보 중 사용자가 요구한 속성을 모두 선택합니다.
   - 여러 속성을 요구하면 여러 개를 반환합니다.
   - 넓은 '기능/효과'보다 직접 대응하는 구체적인 속성을 우선합니다.

   [속성 정규화 예시]
   - 보습, 보습력, 촉촉함, 수분, 건조하지 않은 → 수분감
   - 발림, 잘 발리는, 부드럽게 펴지는 → 발림성
   - 오래가는, 유지력, 지속되는 → 지속력
   - 커버, 잡티 가림, 가려지는 → 커버력
   - 향, 냄새, 향기 → 향

5. sentiment
   - 부정 리뷰, 단점, 불만, 최악, 별로인 점 → negative
   - 긍정 리뷰, 장점, 만족 의견 → positive
   - 단순한 추천, 좋은 제품, 괜찮은 제품 → none
   -  장단점, 장점과 단점, 긍정과 부정을 모두 요청하면 → none

[브랜드 후보 - 실제 brand_name]
{self._compact_list(brands)}

[상품 카테고리 후보 - 실제 category_names]
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
                        "상품명은 추출하지 마세요. "
                        "브랜드·카테고리·속성·감성만 JSON으로 반환하세요.\n"
                        "반드시 제공된 실제 metadata 후보 목록의 값을 선택하고, "
                        "후보에 없는 값을 생성하지 마세요.\n"
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

    def _extract_metadata_with_python(
        self,
        query: str,
    ) -> dict[str, Any]:
        """
        LLM을 호출하지 않고 질문 원문과 실제 ChromaDB metadata 값을
        비교하여 검색 조건을 추출합니다.

        추출 대상
            1. 브랜드
            2. 상품 카테고리
            3. 분석 카테고리
            4. 속성
            5. 감성

        상품명은 기존 _match_product_names_from_query()에서 별도로 처리합니다.
        """

        query_normalized = normalize_for_match(query)

        # -------------------------------------------------------------------------
        # 1. 브랜드 추출 
        # -------------------------------------------------------------------------
        # 실제 브랜드 목록을 돌면서 질문에 포함되어 있는지 확인
        brand_name = ""

        for value in self.field_vocabularies.get("brand_name", []):
            normalized_value = normalize_for_match(value)

            if (
                len(normalized_value) >= 2
                and normalized_value in query_normalized
            ):
                brand_name = value
                break

        # -------------------------------------------------------------------------
        # 2. 상품 카테고리 추출
        # -------------------------------------------------------------------------
        raw_category_values: list[str] = []

        # 실제 category_names의 하위 카테고리 표현을 질문과 비교합니다.
        for category_token in self.category_token_to_full_values:
            normalized_token = normalize_for_match(category_token)

            if (
                len(normalized_token) >= 2
                and normalized_token in query_normalized
            ):
                raw_category_values.append(category_token)

        # 썬크림 → 선크림, 토너 → 스킨/토너 등의 별칭을 비교합니다.
        for alias, canonical in CATEGORY_ALIASES.items():
            normalized_alias = normalize_for_match(alias)

            if normalized_alias in query_normalized:
                raw_category_values.append(canonical)

        category_names = self._validate_categories(
            unique_nonempty(raw_category_values)
        )

        # -------------------------------------------------------------------------
        # 3. 분석 카테고리 추출
        # -------------------------------------------------------------------------
        analysis_category_name = ""

        ANALYSIS_CATEGORY_ALIASES = {
            "립": "립메이크업",
            "립제품": "립메이크업",
            "립화장품": "립메이크업",

            "아이": "아이메이크업",
            "아이제품": "아이메이크업",

            "베이스": "베이스메이크업",
            "베이스제품": "베이스메이크업",
        }

        # 별칭 먼저 확인
        for alias, canonical in ANALYSIS_CATEGORY_ALIASES.items():
            if normalize_for_match(alias) in query_normalized:
                analysis_category_name = canonical
                break

        # 별칭이 없을 때만 기존 방식 사용
        if not analysis_category_name and not category_names:
            for value in self.field_vocabularies.get(
                "analysis_category_name",
                [],
            ):
                normalized_value = normalize_for_match(value)

                if (
                    len(normalized_value) >= 2
                    and normalized_value in query_normalized
                ):
                    analysis_category_name = value
                    break

        # -------------------------------------------------------------------------
        # 4. 속성 추출
        # -------------------------------------------------------------------------
        # -------------------------------------------------------------------------
        # 브랜드명 안의 단어가 속성(alias)으로 잘못 인식되는 것을 방지합니다.
        #
        # 예)
        #   컬러그램 립제품 알려줘
        #   -> "컬러"가 발색력 alias로 인식되지 않도록
        # -------------------------------------------------------------------------
        attribute_query_normalized = query_normalized

        if brand_name:
            normalized_brand = normalize_for_match(brand_name)

            if normalized_brand:
                attribute_query_normalized = (
                    attribute_query_normalized.replace(
                        normalized_brand,
                        ""
                    )
                )
        
        raw_attribute_values: list[str] = []

        # 실제 속성명이 질문에 포함됐는지 먼저 확인합니다.
        for value in self.field_vocabularies.get(
            "attribute_name",
            [],
        ):
            normalized_value = normalize_for_match(value)

            if (
                len(normalized_value) >= 2
                and normalized_value in attribute_query_normalized
            ):
                raw_attribute_values.append(value)

        # 사용자 표현과 실제 속성명의 차이를 보정합니다.
        attribute_aliases = {
            "기능/효과": {
                "기능", "효과", "기능효과", "효능"
            },

            "밀착력": {
                "밀착력", "밀착", "잘밀착", "들뜸"
            },

            "발림성": {
                "발림성", "발림", "잘발리는",
                "부드럽게발리는", "뻑뻑"
            },

            "발색력": {
                "발색력", "발색", "색감",
                "컬러", "색상"
            },

            "사용감": {
                "사용감", "사용하기", "사용할때",
                "사용편의", "편리함"
            },

            "수분감": {
                "수분감", "수분", "보습",
                "보습력", "촉촉", "촉촉함",
                "건조"
            },

            "자극성": {
                "자극성", "자극도", "자극",
                "따가움", "따가운", "저자극",
                "순한"
            },

            "제형": {
                "제형", "질감", "텍스처",
                "묽은", "꾸덕", "크림", "젤"
            },

            "지속력": {
                "지속력", "지속", "유지력",
                "오래가는", "오래가", "무너짐"
            },

            "커버력": {
                "커버력", "커버",
                "가려지는", "잡티가림",
                "모공가림"
            },

            "피부표현": {
                "피부표현", "표현",
                "피부결", "윤광",
                "광", "매트"
            },

            "향": {
                "향", "향기", "냄새", "향료"
            },

            "흡수력": {
                "흡수력", "흡수",
                "스며드는", "스며듦",
                "흡수되는"
            },
        }

        actual_attribute_map = {
            normalize_for_match(value): value
            for value in self.field_vocabularies.get(
                "attribute_name",
                [],
            )
        }

        for canonical, aliases in attribute_aliases.items():
            has_alias = any(
                normalize_for_match(alias) in attribute_query_normalized
                for alias in aliases
            )

            if not has_alias:
                continue

            actual_value = actual_attribute_map.get(
                normalize_for_match(canonical)
            )

            # ChromaDB에 실제 존재하는 속성만 추가합니다.
            if actual_value:
                raw_attribute_values.append(actual_value)

        attribute_name = unique_nonempty(raw_attribute_values)

        # -------------------------------------------------------------------------
        # 5. 감성 추출
        # -------------------------------------------------------------------------
        positive_terms = {
            "긍정",
            "긍정리뷰",
            "만족",
            "좋은평가",
            "좋은리뷰",
            "장점",
            "좋은점",
            "좋은",
            "강점",
            "장점"
        }

        negative_terms = {
            "부정",
            "부정의견",
            "부정리뷰",
            "불만",
            "나쁜평가",
            "나쁜리뷰",
            "개선점",
            "단점",
            "고칠점",
            "아쉬운"
        }

        # 둘 중 긍정만 있으면 -> positive
        has_positive = any(
            normalize_for_match(term) in query_normalized
            for term in positive_terms
        )

        # 둘 중 부정만 있으면 -> negative
        has_negative = any(
            normalize_for_match(term) in query_normalized
            for term in negative_terms
        )

        # 둘다 있거나 둘다 없으면 -> none
        if has_positive and not has_negative:
            sentiment = "positive"
        elif has_negative and not has_positive:
            sentiment = "negative"
        else:
            sentiment = "none"

        result = {
            "brand_name": brand_name,
            "category_names": category_names,
            "analysis_category_name": analysis_category_name,
            "attribute_name": attribute_name,
            "sentiment": sentiment,
        }

        print(
            "[INFO] Python metadata 선택 결과: "
            + json.dumps(
                result,
                ensure_ascii=False,
            )
        )

        return result

    
    def _validate_exact_values(
        self,
        key: str,
        raw_values: list[str],
    ) -> list[str]:
        """LLM 결과가 실제 ChromaDB metadata 값과 일치하는지 검증합니다."""

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
        LLM이 선택한 브랜드를 실제 ChromaDB 값과 검증합니다.

        LLM 값이 정확히 일치하지 않으면 질문 원문에 실제 브랜드명이
        포함되어 있는지 한 번 더 확인합니다.
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

    def _validate_categories(
        self,
        raw_values: list[str],
    ) -> list[str]:
        """
        LLM이 반환한 category_names를 실제 ChromaDB 값과 검증합니다.

        전체 저장값이 정확히 일치하지 않으면 alias와 하위 카테고리 토큰을 사용해
        실제 전체 category_names 값으로 보정합니다.
        """

        validated: set[str] = set()

        for raw_value in raw_values:
            original = str(raw_value or "").strip()
            normalized = normalize_for_match(original)

            if not normalized:
                continue

            exact_full_value = self.category_full_normalized_map.get(normalized)

            if exact_full_value:
                validated.add(exact_full_value)
                continue

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
        """positive/negative를 실제 ChromaDB sentiment 저장값으로 변환합니다."""

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

    # 상품명 토큰 추출
    @staticmethod
    def _raw_query_tokens(query: str) -> list[str]:
        """
        상품명 매칭용 토큰을 생성합니다.

        - 원문기반 토큰 + kiwi기반 토큰
        - 원형 토큰은 조사만 제거하여 보존합니다.
        - Kiwi 토큰은 명사 계열만 사용합니다.
        - 원형 표현과 형태소 분석 결과를 함께 사용하여
          '유채꿀', '멀티오일' 같은 상품 고유 표현을 최대한 보존합니다.
        """

        cleaned_query = str(query or "").strip().lower()

        if not cleaned_query:
            return []

        # ---------------------------------------------------------------------
        # 1. 공백·문장부호 기준 원형 토큰
        # ---------------------------------------------------------------------
        raw_tokens = re.findall(
            r"[가-힣A-Za-z0-9+]+",
            cleaned_query,
        )

        # 긴 조사부터 제거해야 "에서"가 "에"보다 먼저 처리됩니다.
        particle_pattern = re.compile(
            r"(으로부터|에게서|한테서|으로써|으로서|까지|부터|에게|한테|"
            r"에서|보다|처럼|만큼|으로|라고|이라도|라도|이며|이고|과|와|"
            r"은|는|이|가|을|를|의|에|로|도|만)$"
        )

        normalized_raw_tokens: list[str] = []

        for token in raw_tokens:
            normalized = normalize_for_match(token)

            if not normalized:
                continue

            normalized = particle_pattern.sub("", normalized)

            if normalized:
                normalized_raw_tokens.append(normalized)

        # ---------------------------------------------------------------------
        # 2. Kiwi 명사 토큰
        # ---------------------------------------------------------------------
        kiwi_noun_tokens: list[str] = []

        try:
            kiwi = get_kiwi()

            for token in kiwi.tokenize(cleaned_query):
                # 일반 명사, 고유 명사, 영어, 숫자만 사용합니다.
                if token.tag not in {"NNG", "NNP", "SL", "SN"}:
                    continue

                normalized = normalize_for_match(token.form)

                if not normalized:
                    continue

                if len(normalized) == 1 and token.tag in {"NNG", "NNP"}:
                    continue

                kiwi_noun_tokens.append(normalized)

        except Exception as error:
            print(f"[WARNING] 상품명 매칭용 Kiwi 토큰 추출 실패: {error}")

        return unique_nonempty(
            normalized_raw_tokens + kiwi_noun_tokens
        )

    def _extract_product_query_tokens(
        self,
        query: str,
        brand_values: list[str],
        attribute_values: list[str],
    ) -> tuple[list[str], list[str]]:
        """
        질문에서 상품 식별 토큰과 일반 상품 종류 토큰을 분리합니다.

        distinctive_tokens:
            실제 상품 라인명이나 고유 표현일 가능성이 높은 단어
            예: 어린, 녹차, 뽀얀쌀, 유채꿀, 다이브인

        generic_tokens:
            카테고리나 일반 상품 종류
            예: 클렌, 클렌징폼, 토너, 세럼
        """

        tokens = self._raw_query_tokens(query)

        blocked_terms = {
            normalize_for_match(value)
            for value in (
                PRODUCT_ATTRIBUTE_TERMS
                | PRODUCT_SENTIMENT_TERMS
                | PRODUCT_SALES_TERMS
                | PRODUCT_QUERY_STOP_TERMS
            )
        }

        # LLM이 선택한 실제 속성명도 상품명 토큰에서 제거합니다.
        blocked_terms.update(
            normalize_for_match(value)
            for value in attribute_values
        )

        # 브랜드 전체명과 브랜드가 Kiwi에서 분리된 토큰을 제거합니다.
        for brand in brand_values:
            blocked_terms.add(normalize_for_match(brand))
            blocked_terms.update(self._raw_query_tokens(brand))

        generic_terms = {
            normalize_for_match(value)
            for value in PRODUCT_GENERIC_TERMS
        }

        distinctive_tokens: list[str] = []
        generic_tokens: list[str] = []

        for token in tokens:

            if not token or token.isdigit():
                continue

            # 용량 표현과 숫자 중심 표현 제거
            if re.fullmatch(r"\d+(?:ml|g|매|개|입)?", token, re.IGNORECASE):
                continue

            is_blocked = any(
                token == blocked
                or (
                    len(blocked) >= 3
                    and blocked in token
                )
                for blocked in blocked_terms
            )

            if is_blocked:
                continue

            if token in generic_terms:
                generic_tokens.append(token)
                continue

            # 한 글자 한글 토큰은 노이즈가 많으므로 제외
            if len(token) < 2 and re.fullmatch(r"[가-힣]", token):
                continue

            distinctive_tokens.append(token)

        return (
            unique_nonempty(distinctive_tokens),
            unique_nonempty(generic_tokens),
        )

    def _product_matches_context(
        self,
        product_name: str,
        brand_values: list[str],
        category_values: list[str],
    ) -> bool:
        """상품의 실제 브랜드·카테고리가 LLM 필터 조건과 맞는지 확인합니다."""

        record = self.product_metadata_map.get(
            product_name,
            {
                "brand_name": set(),
                "category_names": set(),
            },
        )

        if brand_values:
            product_brands = record.get("brand_name", set())

            if not product_brands.intersection(brand_values):
                return False

        # category_values는 여기서 강제 제외 조건으로 사용하지 않습니다.
        # 사용자가 "클렌"처럼 줄여 말하면 LLM이 실제 상품의 세부 카테고리를
        # 다르게 선택할 수 있기 때문입니다. 카테고리는 아래 점수 계산에서
        # 일치할 때만 가산점으로 사용하고, 상품명 토큰을 우선합니다.

        return True

    def _match_product_names_from_query(
        self,
        query: str,
        brand_values: list[str],
        category_values: list[str],
        attribute_values: list[str],
    ) -> list[str]:
        """
        질문 원문과 실제 ChromaDB product_name을 Python으로 비교합니다.

        선택 순서
        ------------------------------------------------------------------
        1. 질문의 상품명 표현이 실제 product_name에 직접 포함되는지 우선 확인
        2. 직접 매칭이 실패하면 기존 토큰 기반 점수 매칭 수행
        3. 브랜드·카테고리가 있으면 후보 상품 범위를 제한
        """

        distinctive_tokens, generic_tokens = self._extract_product_query_tokens(
            query=query,
            brand_values=brand_values,
            attribute_values=attribute_values,
        )

        print(
            "[DEBUG] Python 상품명 고유 토큰: "
            + (
                ", ".join(distinctive_tokens)
                if distinctive_tokens
                else "(없음)"
            )
        )

        print(
            "[DEBUG] Python 상품 종류 토큰: "
            + (
                ", ".join(generic_tokens)
                if generic_tokens
                else "(없음)"
            )
        )

        # 일반 상품 종류만 있으면 특정 상품으로 판단하지 않습니다.
        if not distinctive_tokens:
            return []

        # =====================================================================
        # 1. 실제 상품명 직접 부분 매칭 우선
        # =====================================================================

        direct_matches: list[str] = []

        # 고유 토큰 중 가장 긴 표현을 우선 사용합니다.
        #
        # 예:
        # distinctive_tokens = ["블랙쿠션", "블랙"]
        #
        # 실제 상품명:
        # "[프리미엄 1위] 헤라 블랙 쿠션 파운데이션 기획 ..."
        #
        # normalize 후:
        # "블랙쿠션" in "프리미엄1위헤라블랙쿠션파운데이션기획..."
        # → True

        sorted_distinctive_tokens = sorted(
            distinctive_tokens,
            key=len,
            reverse=True,
        )

        longest_token = sorted_distinctive_tokens[0]

        for product_name in self.product_name_values:

            # 브랜드 / 카테고리 조건 확인
            if not self._product_matches_context(
                product_name=product_name,
                brand_values=brand_values,
                category_values=category_values,
            ):
                continue

            normalized_product = normalize_for_match(product_name)

            # 가장 긴 고유 토큰이 실제 상품명에 포함되는지 확인
            if (
                len(longest_token) >= 3
                and longest_token in normalized_product
            ):
                direct_matches.append(product_name)

        direct_matches = unique_nonempty(direct_matches)

        # 직접 매칭 성공
        if direct_matches:

            # 너무 많은 상품이 걸리지 않았다면 바로 사용
            if len(direct_matches) <= 20:

                print("[DEBUG] Python 상품명 직접 매칭 결과:")

                for product_name in direct_matches:
                    print(f"        - {product_name}")

                return direct_matches

        # =====================================================================
        # 2. 직접 매칭 실패 → 기존 토큰 기반 점수 매칭
        # =====================================================================

        scored: list[tuple[float, int, int, str]] = []

        for product_name in self.product_name_values:

            if not self._product_matches_context(
                product_name=product_name,
                brand_values=brand_values,
                category_values=category_values,
            ):
                continue

            normalized_product = normalize_for_match(product_name)

            matched_distinctive = [
                token
                for token in distinctive_tokens
                if token in normalized_product
            ]

            matched_generic = [
                token
                for token in generic_tokens
                if token in normalized_product
            ]

            distinctive_count = len(matched_distinctive)
            total_distinctive = len(distinctive_tokens)

            if distinctive_count == 0:
                continue

            # -------------------------------------------------------------
            # 기존 fallback 기준
            # -------------------------------------------------------------

            if total_distinctive >= 2:

                coverage = distinctive_count / total_distinctive

                if distinctive_count < 2 or coverage < 0.60:
                    continue

            else:
                coverage = 1.0

            # -------------------------------------------------------------
            # 기존 점수 계산
            # -------------------------------------------------------------

            record = self.product_metadata_map.get(
                product_name,
                {
                    "brand_name": set(),
                    "category_names": set(),
                },
            )

            category_bonus = 0.0

            if (
                category_values
                and record.get(
                    "category_names",
                    set(),
                ).intersection(category_values)
            ):
                category_bonus = 2.0

            score = (
                sum(
                    min(len(token), 10)
                    for token in matched_distinctive
                )
                + (coverage * 10.0)
                + (len(matched_generic) * 0.75)
                + category_bonus
            )

            # 고유 토큰이 이어진 형태로 상품명에 있으면 추가 점수
            joined_distinctive = "".join(distinctive_tokens)

            if (
                len(joined_distinctive) >= 3
                and joined_distinctive in normalized_product
            ):
                score += 5.0

            scored.append(
                (
                    score,
                    distinctive_count,
                    len(matched_generic),
                    product_name,
                )
            )

        # =====================================================================
        # 3. 매칭 결과 없음
        # =====================================================================

        if not scored:

            print("[DEBUG] Python 상품명 매칭 결과: (없음)")

            return []

        # =====================================================================
        # 4. 점수가 높은 상품 선택
        # =====================================================================

        scored.sort(
            key=lambda row: (
                row[0],
                row[1],
                row[2],
                -len(row[3]),
            ),
            reverse=True,
        )

        best_score = scored[0][0]
        best_distinctive_count = scored[0][1]

        # 같은 라인의 용량·기획 상품은 점수가 비슷하므로 함께 유지
        selected = [
            product_name
            for score, distinctive_count, _, product_name in scored
            if distinctive_count == best_distinctive_count
            and score >= best_score - 1.0
        ]

        selected = unique_nonempty(selected)

        # 지나치게 많은 상품이 선택되면
        # 특정 상품 질문으로 판단하지 않습니다.
        if len(selected) > 20:

            print(
                f"[DEBUG] Python 상품명 매칭 후보가 "
                f"{len(selected):,}개로 너무 많아 "
                "상품명 필터를 적용하지 않습니다."
            )

            return []

        # =====================================================================
        # 5. 최종 결과 출력
        # =====================================================================

        print("[DEBUG] Python 상품명 토큰 매칭 결과:")

        for product_name in selected:
            print(f"        - {product_name}")

        return selected

    def extract(self, query: str) -> MetadataFilterResult:
        """
        사용자 질문에서 LLM + Python 기반 Metadata Filter를 생성합니다.

        처리 순서
            1. LLM으로 브랜드·카테고리·분석 카테고리·속성·감성 추출
            2. 실제 ChromaDB metadata 값과 검증
            3. 개선점/장점 등의 검색 의도를 Python에서 감성 조건으로 보정
            4. 상품명은 Python이 질문 원문과 실제 상품명을 비교하여 추출
            5. 최종 Chroma where 조건 생성
        """

        cleaned_query = query.strip()

        if not cleaned_query:
            return MetadataFilterResult()

        if self.use_llm_metadata_filter:
            try:
                metadata_result = self._call_llm(cleaned_query)

                print(
                    "[INFO] LLM metadata 선택 결과: "
                    + json.dumps(
                        metadata_result,
                        ensure_ascii=False,
                    )
                )

            except Exception as error:
                print(
                    f"[WARNING] LLM Metadata Filter 추출 실패: {error}"
                )
                print(
                    "[WARNING] Python Metadata Filter로 대체합니다."
                )

                metadata_result = self._extract_metadata_with_python(
                    cleaned_query
                )

        else:
            metadata_result = self._extract_metadata_with_python(
                cleaned_query
            )

        # 아래 기존 코드가 llm_result라는 변수명을 사용하므로
        # 호환을 위해 연결합니다.
        llm_result = metadata_result

        field_values: dict[str, list[str]] = {}

        # -------------------------------------------------------------------------
        # 1. 브랜드 검증
        # -------------------------------------------------------------------------
        brand_values = self._validate_brand(
            str(llm_result.get("brand_name") or ""),
            cleaned_query,
        )

        if brand_values:
            field_values["brand_name"] = brand_values

        # -------------------------------------------------------------------------
        # 2. 상품 카테고리 검증
        # -------------------------------------------------------------------------
        category_values = self._validate_categories(
            list(llm_result.get("category_names") or [])
        )

        if category_values:
            field_values[CATEGORY_FILTER_FIELD] = category_values

        # -------------------------------------------------------------------------
        # 3. 구체적인 상품 카테고리가 없을 때만 분석 카테고리 사용
        # -------------------------------------------------------------------------
        if not category_values:
            analysis_values = self._validate_exact_values(
                "analysis_category_name",
                [
                    str(
                        llm_result.get("analysis_category_name")
                        or ""
                    )
                ],
            )

            if analysis_values:
                field_values["analysis_category_name"] = analysis_values[:1]

        # -------------------------------------------------------------------------
        # 4. 속성 검증
        # -------------------------------------------------------------------------
        attribute_values = self._validate_exact_values(
            "attribute_name",
            list(llm_result.get("attribute_name") or []),
        )

        # -------------------------------------------------------------------------
        # 4-1. 개선점·장점 등 검색 의도 보정
        #
        # 개선점, 단점, 장점 등은 제품 속성이 아니라
        # 긍정/부정 리뷰를 요청하는 검색 의도입니다.
        #
        # 소형 LLM이 "개선점"을 "기능/효과" 등의 속성으로 잘못 선택해도
        # Python이 질문 원문을 확인하여 속성 조건을 제거하고 감성을 보정합니다.
        # -------------------------------------------------------------------------
        intent_only_terms = {
            "개선점",
            "개선할점",
            "개선할 점",
            "아쉬운점",
            "아쉬운 점",
            "문제점",
            "장점",
            "단점",
            "좋은점",
            "좋은 점",
            "강점",
        }

        attribute_values = [
            value
            for value in attribute_values
            if value not in intent_only_terms
        ]

        query_no_space = normalize_for_match(cleaned_query)

        negative_intent_terms = {
            "개선점",
            "개선할점",
            "개선사항",
            "아쉬운점",
            "문제점",
            "단점",
            "불편한점",
            "불만",
            "최악",
        }

        positive_intent_terms = {
            "장점",
            "좋은점",
            "강점",
            "만족한점",
            "잘한점",
        }

        has_negative_intent = any(
            normalize_for_match(term) in query_no_space
            for term in negative_intent_terms
        )

        has_positive_intent = any(
            normalize_for_match(term) in query_no_space
            for term in positive_intent_terms
        )

        # 긍정과 부정을 모두 요청하는 질문인지 먼저 확인합니다.
        both_sentiment_terms = {
            "장단점",
            "긍정부정",
            "긍정과부정",
            "긍정및부정",
            "장점과단점",
            "장점및단점",
        }

        has_both_sentiments = (
            has_positive_intent
            and has_negative_intent
        ) or any(
            normalize_for_match(term) in query_no_space
            for term in both_sentiment_terms
        )

        if has_both_sentiments:
            # 장점과 단점을 모두 요청하므로 감성 필터를 적용하지 않습니다.
            llm_result["sentiment"] = "none"
            attribute_values = []

            print(
                "[DEBUG] Python 검색 의도 보정: "
                "장점+단점 질문 → 속성 필터 제거, 감성 필터 없음"
            )

        elif has_negative_intent:
            # 개선점과 단점은 전체 부정 의견을 요구합니다.
            llm_result["sentiment"] = "negative"
            attribute_values = []

            print(
                "[DEBUG] Python 검색 의도 보정: "
                "개선/단점 질문 → 속성 필터 제거, 감성=negative"
            )

        elif has_positive_intent:
            # 장점은 전체 긍정 의견을 요구합니다.
            llm_result["sentiment"] = "positive"
            attribute_values = []

            print(
                "[DEBUG] Python 검색 의도 보정: "
                "장점 질문 → 속성 필터 제거, 감성=positive"
            )

        if attribute_values:
            field_values["attribute_name"] = attribute_values

        # -------------------------------------------------------------------------
        # 5. 감성 검증
        #
        # 반드시 위의 검색 의도 보정 이후에 실행해야 합니다.
        # -------------------------------------------------------------------------
        sentiment_values = self._validate_sentiment(
            str(llm_result.get("sentiment") or "none")
        )

        if sentiment_values:
            field_values[SENTIMENT_FILTER_FIELD] = sentiment_values

        # -------------------------------------------------------------------------
        # 6. 상품명은 LLM 결과를 사용하지 않고 Python으로 직접 찾습니다.
        # -------------------------------------------------------------------------
        product_name_values = self._match_product_names_from_query(
            query=cleaned_query,
            brand_values=brand_values,
            category_values=category_values,
            attribute_values=attribute_values,
        )

        if product_name_values:
            field_values[PRODUCT_NAME_FILTER_FIELD] = product_name_values

            # 상품명이 정확히 특정되면 상품명이 가장 강한 조건입니다.
            # LLM 카테고리가 실제 상품 카테고리와 충돌하는 경우에는
            # 잘못된 AND 조건으로 검색 결과가 0개가 되지 않도록
            # 상품명 조건을 우선하고 카테고리 필터를 제거합니다.
            if category_values:
                category_is_consistent = all(
                    self.product_metadata_map.get(
                        product_name,
                        {
                            "category_names": set(),
                        },
                    )
                    .get(
                        "category_names",
                        set(),
                    )
                    .intersection(category_values)
                    for product_name in product_name_values
                )

                if not category_is_consistent:
                    print(
                        "[DEBUG] Python 상품명과 LLM 상품 카테고리가 충돌하여 "
                        "상품명 조건을 우선하고 카테고리 필터를 제거합니다."
                    )

                    field_values.pop(
                        CATEGORY_FILTER_FIELD,
                        None,
                    )

        # -------------------------------------------------------------------------
        # 7. 최종 Metadata Filter 반환
        # -------------------------------------------------------------------------
        return MetadataFilterResult(
            field_values=field_values,
            chroma_where=self._build_chroma_where(
                field_values
            ),
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

    # 1. 질문에서 Kiwi 키워드 추출 + 질문용 불용어 제거
    keywords = extract_query_keywords(cleaned_query)

    # 2. LLM 또는 Python으로 질문을 분석하고
    #   실제 Chroma metadata 값으로 검증하여 Filter 생성
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
    LLM과 Python이 어떤 조건을 선택했고 어떤 조건은 선택하지 않았는지 확인할 수 있습니다.
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

        # Chroma metadata는 LLM 후보 검증과 Python 상품명 매칭에 함께 사용합니다.
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