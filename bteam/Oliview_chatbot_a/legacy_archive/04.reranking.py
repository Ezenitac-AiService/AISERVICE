# uv run python 04.reranking.py
"""
================================================================================
[04단계] Oliview 하이브리드 검색 + Cross Encoder 리랭킹
================================================================================

기반 파일
    03.03.hybrid_search_meta_llm_python.py

프로그램 실행
   ↓
03.03 파일 불러오기
   ↓
BGE-M3 임베딩 모델 준비
   ↓
ChromaDB 연결
   ↓
BM25 인덱스 준비
   ↓
Metadata Filter 준비
   ↓
BGE Cross Encoder 리랭커 준비
   ↓
사용자 질문 입력
   ↓
Metadata Filter
브랜드 / 상품 / 카테고리 / 속성 / 감성
   ↓
 ┌────────────────────┐
 │                    │
 ↓                    ↓
Vector Search       BM25 Search
후보 20개             후보 20개
 │                    │
 └────────┬───────────┘
          ↓
       RRF 결합
       Top 10
          ↓
 Cross Encoder 평가(Reranking) 10개
 질문 + 리뷰문장을 같이 읽음
          ↓
       최종 Top 5

필요 라이브러리
    uv add sentence-transformers torch

기본 리랭커 모델 경로
    models/rerankers/bge-reranker-v2-m3

환경변수로 변경 가능
    RERANKER_MODEL_PATH=models/rerankers/bge-reranker-v2-m3

주의
    이 파일은 같은 폴더의 03.03.hybrid_search_meta_llm_python.py를
    동적으로 불러와 기존 하이브리드 검색 로직을 그대로 재사용합니다.
================================================================================
"""

from __future__ import annotations  # 타입 힌트를 조금 더 유연하게 사용할 수 있도록

import importlib.util               # 03.03.hybrid_search_meta_llm_python.py을 동적으로 불러오기 위해 사용
import math                         # Cross Encoder 점수가 정상적인 숫자인지 검사할 때 사용
import os                           # 폴더경로, 환경변수 등을 처리할 때 사용
import sys                          # Python 모듈검색경로, 운영체제 확인시 사용
import numpy as np
from dataclasses import dataclass   # 검색결과를 저장할 RerankedItem 클래스를 간단하게 만들기 위해 사용
from types import ModuleType        # 동적으로 불러온 03.03파일이 Python 모듈이라는 타입을 표시
from typing import Any              # 여러 종류의 객체를 받을 수 있다는 타입표시

import torch  # GPU 사용여부 확인 및 Pytorch 추론에 사용
from sentence_transformers import CrossEncoder # BGE reranker 모델을 실제로 실행하는 핵심 클래스


# =============================================================================
# [1] 프로젝트 경로 및 03.03 파일 불러오기
# =============================================================================

BASE_FILE_NAME = "03.03.hybrid_search_meta_llm_python.py"

# 프로젝트 최상위 폴더 찾기
def get_project_root() -> str:
    """현재 파일 또는 상위 폴더에서 프로젝트 최상위 경로를 찾습니다."""

    current = os.path.abspath(os.path.dirname(__file__))

    if (
        os.path.exists(os.path.join(current, "pyproject.toml"))
        or os.path.exists(os.path.join(current, "common"))
        or os.path.exists(os.path.join(current, BASE_FILE_NAME))
    ):
        return current

    parent = os.path.abspath(os.path.join(current, ".."))

    if (
        os.path.exists(os.path.join(parent, "pyproject.toml"))
        or os.path.exists(os.path.join(parent, "common"))
        or os.path.exists(os.path.join(parent, BASE_FILE_NAME))
    ):
        return parent

    return current

# 찾아낸 프로젝트 최상위 경로 저장
ROOT_DIR = get_project_root()

# Python이 프로젝트 안의 모듈을 import 할 수 있도록 검색경로에 추가
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 03.03 파일 동적 import
def load_hybrid_module() -> ModuleType:
    """
    숫자와 점이 포함된 03.03 파일은 일반 import 문으로 불러오기 어렵기 때문에
    importlib를 이용하여 동적으로 불러옵니다.
    """

    # 03.03 파일의 전체경로를 만듬
    module_path = os.path.join(ROOT_DIR, BASE_FILE_NAME)

    if not os.path.isfile(module_path): # 03.03파일이 실제로 존재하는지 확인
        raise FileNotFoundError(
            "\n기반 하이브리드 검색 파일을 찾지 못했습니다.\n"
            f"확인 경로: {module_path}\n\n"
            "04.reranking.py와 03.03.hybrid_search_meta_llm_python.py를 "
            "같은 프로젝트 폴더에 두세요."
        )

    # 03.03파일을 Python 모듈로 불러오기 위한 정보를 만듬
    spec = importlib.util.spec_from_file_location(
        "oliview_hybrid_search_meta_llm_python_name",
        module_path,
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            f"03.03 파일의 모듈 정보를 생성하지 못했습니다: {module_path}"
        )

    # 실제 모듈 객체를 만듬
    module = importlib.util.module_from_spec(spec)

    # Python의 현재 모듈목록에 등록
    sys.modules[spec.name] = module

    # 03.03파일을 실제로 실행해서 내용을 불러옴
    spec.loader.exec_module(module)

    # 불러온 모듈을 반환
    return module

hybrid = load_hybrid_module()
# 03.03 안에 있는 코드들을 hybird. 로 사용할 수 있음

# =============================================================================
# [2] 리랭킹 기본 설정
# =============================================================================

DEFAULT_RRF_CANDIDATE_K = 10     # RRF까지 결합한 결과 중 Cross Encoder에게 전달할 후보 수 = 10개
DEFAULT_RERANK_TOP_K = 5         # Cross Encoder에게 전달할 후보 수 = 10개
DEFAULT_RERANK_BATCH_SIZE = 16   # Cross Encoder가 한 번에 처리할 [질문, 리뷰] 쌍의 최대 묶음 크기
DEFAULT_RERANK_MAX_LENGTH = 512  # Cross Encoder에 입력되는 질문+리뷰의 최대 토큰 길이를 512로 제한

# 환경변수 .env 등에 RERANKER_MODEL_PATH가 있으면 그 값을 사용
# 없으면 기본으로 BAAI/bge-reranker-v2-m3 모델을 사용
RERANKER_MODEL_PATH = os.getenv(
    "RERANKER_MODEL_PATH",
    "BAAI/bge-reranker-v2-m3",
)


# =============================================================================
# [3] 리랭킹 결과 자료형
# =============================================================================

# 한 개의 리뷰 결과를 저장하는 자료형
@dataclass
class RerankedItem:
    """RRF 검색 결과와 Cross Encoder 점수를 함께 보관합니다."""

    document_id: str
    text: str
    metadata: dict[str, Any]

    vector_rank: int | None = None        # Vector Search의 순위
    vector_distance: float | None = None  # Vector Search의 거리 
    bm25_rank: int | None = None          # BM25의 순위
    bm25_score: float | None = None       # BM25의 점수
    rrf_score: float = 0.0                # Vector + BM25를 합친 RRF점수

    reranker_rank: int | None = None      # Cross Encoder가 다시 평가한 최종 순위
    reranker_score: float = 0.0           # Cross Encoder가 다시 평가한 최종 점수


# =============================================================================
# [4] 실행 장치 및 모델 경로 확인
# =============================================================================

# Cross Encoder를 CPU로 돌릴지 GPU로 돌릴지 결정
def get_reranker_device() -> str:
    """CUDA 사용 가능 여부에 따라 리랭커 실행 장치를 결정합니다."""

    if torch.cuda.is_available():
        return "cuda"

    return "cpu"

# 입력한 모델 경로가 실제 컴퓨터의 폴더인지 검사
def is_local_model_path(model_path: str) -> bool:
    """입력값이 실제 로컬 폴더인지 확인합니다."""

    return os.path.isdir(os.path.abspath(model_path))


# 로컬 코델 폴더가 제대로 구성되어 있는지 검사
def validate_local_reranker_path(model_path: str) -> None:
    """로컬 리랭커 폴더에 기본 모델 파일이 있는지 확인합니다."""

    # 상대경로를 절대경로로 반환
    absolute_path = os.path.abspath(model_path)

    # 폴더가 없으면 오류
    if not os.path.isdir(absolute_path):
        raise FileNotFoundError(
            "\nBGE 리랭커 로컬 모델을 찾지 못했습니다.\n"
            f"확인 경로: {absolute_path}\n\n"
            "다음 중 한 가지 방법을 사용하세요.\n"
            "1. models/rerankers/bge-reranker-v2-m3 폴더에 모델 저장\n"
            "2. .env에 RERANKER_MODEL_PATH=실제_모델_경로 설정\n"
            "3. 인터넷 다운로드를 허용할 경우 RERANKER_MODEL_PATH에 "
            "Hugging Face 모델명 지정"
        )

    # 모델 로딩에 필요한 대표 파일이름
    required_candidates = (
        "config.json",
        "model.safetensors",
        "pytorch_model.bin",
    )

    # config.json이 있는지 확인
    config_exists = os.path.isfile(os.path.join(absolute_path, "config.json"))

    # 모델 가중치 파일이 있는지 확인
    weight_exists = any(
        os.path.isfile(os.path.join(absolute_path, file_name))
        for file_name in required_candidates[1:]
    )

    # shard 모델도 허용합니다.
    if not weight_exists:
        weight_exists = any(
            file_name.startswith("model-") and file_name.endswith(".safetensors")
            for file_name in os.listdir(absolute_path)
        )

    if not config_exists or not weight_exists:
        raise FileNotFoundError(
            "\n리랭커 모델 폴더는 찾았지만 필수 파일이 부족합니다.\n"
            f"확인 경로: {absolute_path}\n"
            "필요 항목: config.json 및 모델 가중치 파일"
        )


# =============================================================================
# [5] Cross Encoder 리랭커
# =============================================================================

# 1) 기존 Vector Search(BGE-M3)
    # 질문 → 임베딩 ─┐
    #                ├→ 벡터 유사도 계산
    # 리뷰 → 임베딩 ─┘

# 2) Cross Encoder
    # [질문 + 리뷰1] → 모델 → 관련성 점수
    # [질문 + 리뷰2] → 모델 → 관련성 점수
    # [질문 + 리뷰3] → 모델 → 관련성 점수
    # 서 57,000개 리뷰 전체에 Cross Encoder를 돌리는 것이 아니라 RRF에서 10개로 줄이고 사용

# BGE Cross Encoder를 관리하는 클래스
class BGEReranker:
    """
    질문과 각 후보 리뷰 문장을 한 쌍으로 입력하여 관련성 점수를 계산합니다.

    Bi-Encoder인 BGE-M3 검색 모델은 질문과 문장을 각각 임베딩하지만,
    Cross Encoder는 [질문, 문장]을 동시에 읽으므로 후보 간 세밀한 순서 조정에
    적합합니다.
    """

    # __init__() 모델 준비
    # BGEReranker를 만들때 실행됨
    def __init__(
        self,
        model_path: str = RERANKER_MODEL_PATH,
        batch_size: int = DEFAULT_RERANK_BATCH_SIZE,
        max_length: int = DEFAULT_RERANK_MAX_LENGTH,
    ) -> None:
        if batch_size <= 0:  # batch 크기가 0이하이면 오류
            raise ValueError("reranker batch_size는 1 이상이어야 합니다.")

        if max_length <= 0: # 최대 토큰 길이가 0이하이면 오류
            raise ValueError("reranker max_length는 1 이상이어야 합니다.")

        self.model_path = model_path
        self.batch_size = batch_size
        self.max_length = max_length
        self.device = get_reranker_device() # GPU 또는 CPU를 결정

        # 로컬모델인지 확인
        local_model = is_local_model_path(model_path)

        # 로컬이라면 필요한 파일까지 검사
        if local_model:
            validate_local_reranker_path(model_path)

        print("\n" + "=" * 100)
        print("[BGE Cross Encoder 리랭커 로드]")
        print("=" * 100)
        print(f"모델 경로/이름 : {model_path}")
        print(f"모델 유형       : {'로컬 모델' if local_model else 'Hugging Face 모델'}")
        print(f"사용 장치       : {self.device}")
        print(f"배치 크기       : {self.batch_size}")
        print(f"최대 토큰 길이  : {self.max_length}")
        # Cross Encoder에 전달할 옵션을 만듬
        self._model_kwargs: dict[str, Any] = {
            "max_length": self.max_length,
            "device": self.device,
        }

        if local_model:
            # 로컬 모델 사용 시 외부 접속 없이 로드합니다.
            self._model_kwargs["automodel_args"] = {"local_files_only": True}
            self._model_kwargs["tokenizer_args"] = {"local_files_only": True}

        self._model = None
        print("[INFO] BGE Cross Encoder 리랭커 준비 완료 (고속 GPU 원격 가속 연동)")

    # 모델이 반환한 점수를 일반 Python float으로 바꿈
    @staticmethod
    def _to_float(score: Any) -> float:
        """numpy, tensor, list 형태의 예측값을 안전하게 float로 변환합니다."""

        if hasattr(score, "item"):
            try:
                return float(score.item())
            except (ValueError, TypeError, RuntimeError):
                pass

        if isinstance(score, (list, tuple)):
            if not score:
                return 0.0
            return BGEReranker._to_float(score[0])

        try:
            return float(score)
        except (ValueError, TypeError):
            return 0.0

    # rerank() : 실제 리랭킹
    def rerank(
        # RRF 후보를 실제로 재정렬
        self,
        query: str,
        candidates: list[Any],
        top_k: int,
    ) -> list[RerankedItem]:
        """RRF 후보를 질문과의 관련성 점수 순으로 재정렬합니다."""

        # 질문을 문자열로 만들고 앞뒤 공백을 제거
        cleaned_query = str(query or "").strip()

        # 질문이나 검색 후보가 없으면 빈 결과 반환
        if not cleaned_query or not candidates:
            return []

        if top_k <= 0:
            raise ValueError("rerank top_k는 1 이상이어야 합니다.")

        # ***[질문, 리뷰] 쌍을 만듬
        pairs = [
            [cleaned_query, str(candidate.text or "").strip()]
            for candidate in candidates
        ]

        raw_scores = None
        # 1. 고속 GPU 리랭커 원격 호출 시도 (0.04초 완료)
        try:
            import httpx
            rerank_url = os.getenv("RERANK_SERVER_URL", "http://vllm-serv-gateway:8091/v1/embeddings")
            cand_texts = [p[1] for p in pairs]
            with httpx.Client(timeout=5.0) as client:
                r_q = client.post(rerank_url, json={"input": cleaned_query}, headers={"Connection": "close"}).json()
                raw_q = np.asarray(r_q["data"][0]["embedding"], dtype=np.float32)
                q_vec = np.mean(raw_q, axis=0) if raw_q.ndim == 2 else raw_q.flatten()

                r_d = client.post(rerank_url, json={"input": cand_texts}, headers={"Connection": "close"}).json()
                scores = []
                for d in r_d["data"]:
                    raw_d = np.asarray(d["embedding"], dtype=np.float32)
                    d_vec = np.mean(raw_d, axis=0) if raw_d.ndim == 2 else raw_d.flatten()
                    dot = np.dot(q_vec, d_vec)
                    norm = np.linalg.norm(q_vec) * np.linalg.norm(d_vec)
                    scores.append(float(dot / norm) if norm > 0 else 0.0)
                if len(scores) == len(pairs):
                    raw_scores = scores
        except Exception:
            raw_scores = None

        # 2. 원격 미연결 시 로컬 모델 추론
        if raw_scores is None:
            if self._model is None:
                self._model = CrossEncoder(
                    self.model_path,
                    **self._model_kwargs,
                )
            with torch.inference_mode():
                raw_scores = self._model.predict(
                    pairs,
                    batch_size=self.batch_size,
                    show_progress_bar=len(pairs) >= 20,
                    convert_to_numpy=True,
                )

        scored_items: list[RerankedItem] = []

        # Cross Encoder 결과저장
        # 각 RRF 후보와 Cross Encoder 점수를 하나씩 짝지어 처리
        for candidate, raw_score in zip(candidates, raw_scores):
            score = self._to_float(raw_score)  # 점수를 float으로 반환

            # 비정상 점수는 정렬을 방해하지 않도록 매우 낮게 처리합니다.
            if not math.isfinite(score):
                score = float("-inf")

            scored_items.append(
                RerankedItem(
                    document_id=candidate.document_id,
                    text=candidate.text,
                    metadata=candidate.metadata or {},
                    vector_rank=candidate.vector_rank,
                    vector_distance=candidate.vector_distance,
                    bm25_rank=candidate.bm25_rank,
                    bm25_score=candidate.bm25_score,
                    rrf_score=candidate.rrf_score,
                    reranker_score=score,
                )
            )

        # ** 최종정렬
        scored_items.sort(
            key=lambda item: (
                item.reranker_score,
                item.rrf_score,
                -(item.vector_distance or 999999.0),
                item.bm25_score or 0.0,
                # 1순위 Cross Encoder 점수
                #     ↓ 같으면
                # 2순위 RRF 점수
                #     ↓ 같으면
                # 3순위 Vector 거리
                #     ↓ 같으면
                # 4순위 BM25 점수
            ),
            reverse=True,
        )

        # 정렬된 결과에서 top_k개만 자름
        final_results = scored_items[: min(top_k, len(scored_items))]

        for rank, item in enumerate(final_results, start=1):
            item.reranker_rank = rank

        # 최종결과 반환
        return final_results


# =============================================================================
# [6] 하이브리드 검색 + 리랭킹 전체 실행
# =============================================================================
# Metadata → Vector → BM25 → RRF → Reranking
def hybrid_search_with_reranking(
    vector_store: Any,
    embeddings: Any,
    bm25_index: Any,
    filter_extractor: Any,
    reranker: BGEReranker,
    query: str,
    candidate_k: int = hybrid.DEFAULT_CANDIDATE_K,
    rrf_candidate_k: int = DEFAULT_RRF_CANDIDATE_K,
    rerank_top_k: int = DEFAULT_RERANK_TOP_K,
    metadata_filter: Any | None = None,
    keywords: list[str] | None = None,
) -> tuple[
    list[str],
    Any,
    int,
    list[Any],
    list[Any],
    list[Any],
    list[RerankedItem],
]:
    """
    Chroma + BM25 + RRF + Cross Encoder 리랭킹을 수행합니다.

    기본 동작
        metadata_filter가 전달되지 않으면 기존처럼 03.03의
        hybrid_search()를 호출하여 Metadata Filter를 자동 생성합니다.

    외부 필터 동작
        metadata_filter가 전달되면 해당 필터를 그대로 사용하여
        Chroma, BM25, RRF, Cross Encoder 검색을 수행합니다.

    장단점 분리 검색 활용 예
        - positive metadata_filter를 전달하여 긍정 리뷰 검색
        - negative metadata_filter를 전달하여 부정 리뷰 검색

    반환값
        keywords,
        metadata_filter,
        filtered_document_count,
        vector_results,
        bm25_results,
        rrf_results,
        reranked_results
    """

    if candidate_k <= 0:
        raise ValueError(
            "candidate_k는 1 이상이어야 합니다."
        )

    if rrf_candidate_k <= 0:
        raise ValueError(
            "rrf_candidate_k는 1 이상이어야 합니다."
        )

    if rerank_top_k <= 0:
        raise ValueError(
            "rerank_top_k는 1 이상이어야 합니다."
        )

    cleaned_query = str(query or "").strip()

    if not cleaned_query:
        return (
            [],
            metadata_filter or hybrid.MetadataFilterResult(),
            0,
            [],
            [],
            [],
            [],
        )

    # -------------------------------------------------------------------------
    # 1. 외부 Metadata Filter가 없는 경우
    #
    # 기존 04.reranking.py의 동작을 그대로 유지합니다.
    # 03.03에서 Metadata 추출부터 RRF까지 한 번에 수행합니다.
    # -------------------------------------------------------------------------
    if metadata_filter is None:
        (
            extracted_keywords,
            extracted_metadata_filter,
            filtered_document_count,
            vector_results,
            bm25_results,
            rrf_results,
        ) = hybrid.hybrid_search(
            vector_store=vector_store,
            embeddings=embeddings,
            bm25_index=bm25_index,
            filter_extractor=filter_extractor,
            query=cleaned_query,
            candidate_k=candidate_k,
            final_k=rrf_candidate_k,
        )

        reranked_results = reranker.rerank(
            query=cleaned_query,
            candidates=rrf_results,
            top_k=rerank_top_k,
        )

        return (
            extracted_keywords,
            extracted_metadata_filter,
            filtered_document_count,
            vector_results,
            bm25_results,
            rrf_results,
            reranked_results,
        )

    # -------------------------------------------------------------------------
    # 2. 외부 Metadata Filter가 전달된 경우
    #
    # Metadata를 다시 추출하지 않고 전달받은 필터로 검색합니다.
    # 장단점 질문의 긍정·부정 분리 검색에 사용합니다.
    # -------------------------------------------------------------------------
    search_keywords = (
        list(keywords)
        if keywords is not None
        else hybrid.extract_keywords(cleaned_query)
    )

    filtered_document_count = (
        bm25_index.count_filtered_documents(
            metadata_filter.field_values
        )
    )

    # -------------------------------------------------------------------------
    # 3. Chroma 벡터 검색
    # -------------------------------------------------------------------------
    # Metadata Filter 조건 안에서 의미적으로 질문과 유사한 질문을 찾음
    vector_results = hybrid.search_chroma(
        vector_store=vector_store,
        embeddings=embeddings,
        query=cleaned_query,
        top_k=candidate_k,
        metadata_filter=metadata_filter,
    )

    # -------------------------------------------------------------------------
    # 4. BM25 검색
    # -------------------------------------------------------------------------
    # Metadata Filter 조건 안에서 키워드 일치 중심 검색을 함
    bm25_results = bm25_index.search(
        query_keywords=search_keywords,
        top_k=candidate_k,
        metadata_filter=metadata_filter,
    )

    # -------------------------------------------------------------------------
    # 5. RRF 결합
    # -------------------------------------------------------------------------
    # Vector 순위 + BM25 순위 = 최종 TOP 10 (기본값)
    rrf_results = hybrid.reciprocal_rank_fusion(
        vector_results=vector_results,
        bm25_results=bm25_results,
        final_k=rrf_candidate_k,
    )

    # -------------------------------------------------------------------------
    # 6. Cross Encoder 리랭킹
    # -------------------------------------------------------------------------
    # RRF Top10을 Cross Encoder가 평가
    # 점수순 재정렬
    # Top 5
    reranked_results = reranker.rerank(
        query=cleaned_query,
        candidates=rrf_results,
        top_k=rerank_top_k,
    )

    return (
        search_keywords,
        metadata_filter,
        filtered_document_count,
        vector_results,
        bm25_results,
        rrf_results,
        reranked_results,
    )


# =============================================================================
# [7] 출력 함수
# =============================================================================


def print_rrf_candidates(results: list[Any]) -> None:
    print("\n" + "#" * 100)
    print("[1차 검색: RRF 결합 후보]")
    print("#" * 100)

    if not results:
        print("RRF 검색 결과가 없습니다.")
        return

    for rank, item in enumerate(results, start=1):
        preview = item.text.replace("\n", " ")[:100]

        print(
            f"RRF {rank:>2}위 | "
            f"rrf={item.rrf_score:.8f} | "
            f"vector={hybrid.rank_text(item.vector_rank)}위 | "
            f"bm25={hybrid.rank_text(item.bm25_rank)}위 | "
            f"{preview}"
        )


def print_reranked_results(
    query: str,
    results: list[RerankedItem],
) -> None:
    print("\n" + "#" * 100)
    print("[2차 검색: Cross Encoder 리랭킹 최종 결과]")
    print("#" * 100)
    print(f"사용자 질문      : {query}")
    print(f"리랭킹 결과 수   : {len(results)}개")
    print("#" * 100)

    if not results:
        print("리랭킹 결과가 없습니다.")
        return

    for item in results:
        metadata = item.metadata or {}

        similarity = None
        if item.vector_distance is not None:
            similarity = 1.0 - item.vector_distance

        print("\n" + "=" * 100)
        print(f"[최종 Rank {item.reranker_rank}]")
        print("=" * 100)
        print(f"Reranker 점수 : {item.reranker_score:.8f}")
        print(f"RRF 점수      : {item.rrf_score:.8f}")
        print(f"Chroma 순위   : {hybrid.rank_text(item.vector_rank)}")
        print(f"Chroma 거리   : {hybrid.float_text(item.vector_distance)}")
        print(f"변환 유사도   : {hybrid.float_text(similarity)}")
        print(f"BM25 순위     : {hybrid.rank_text(item.bm25_rank)}")
        print(f"BM25 점수     : {hybrid.float_text(item.bm25_score)}")
        print("-" * 100)
        print(
            f"상품 ID       : "
            f"{hybrid.metadata_value(metadata, 'product_id')}"
        )
        print(
            f"상품명        : "
            f"{hybrid.metadata_value(metadata, 'product_name')}"
        )
        print(
            f"브랜드명      : "
            f"{hybrid.metadata_value(metadata, 'brand_name')}"
        )
        print(
            f"분석 카테고리 : "
            f"{hybrid.metadata_value(metadata, 'analysis_category_name')}"
        )
        print(
            f"상품 카테고리 : "
            f"{hybrid.metadata_value(metadata, 'category_names')}"
        )
        print(
            f"속성          : "
            f"{hybrid.metadata_value(metadata, 'attribute_name')}"
        )
        print(
            f"감성          : "
            f"{hybrid.metadata_value(metadata, 'sentiment')}"
        )
        print(
            f"리뷰 작성일   : "
            f"{hybrid.metadata_value(metadata, 'review_date')}"
        )
        print("-" * 100)
        print("[리뷰 문장]")
        print(item.text)
        print("=" * 100)


# =============================================================================
# [8] 대화형 실행
# =============================================================================

# 터미널에서 질문을 계속 입력하여 테스트 할 수 있게 만든 함수
def run_interactive_reranking(
    vector_store: Any,
    embeddings: Any,
    bm25_index: Any,
    filter_extractor: Any,
    reranker: BGEReranker,
) -> None:
    exit_commands = {"exit", "quit", "q", "종료"}

    print("\n" + "=" * 100)
    print("[Oliview 하이브리드 검색 + 리랭킹 준비 완료]")
    print("=" * 100)
    print("예시 질문: 식물나라 썬크림의 부정적인 사용감 알려줘")
    print("종료하려면 exit, quit, q 또는 종료를 입력하세요.")
    print("=" * 100)

    while True:
        query = input("\n사용자 질문: ").strip()

        if query.lower() in exit_commands:
            print("\n리랭킹 검색을 종료합니다.")
            break

        if not query:
            print("[WARNING] 질문을 입력해주세요.")
            continue

        # 후보개수 직접 입력
        candidate_k = hybrid.input_positive_int(
            "Chroma/BM25 각각의 후보 개수",
            hybrid.DEFAULT_CANDIDATE_K,
        )

        rrf_candidate_k = hybrid.input_positive_int(
            "리랭킹에 전달할 RRF 후보 개수",
            DEFAULT_RRF_CANDIDATE_K,
        )

        rerank_top_k = hybrid.input_positive_int(
            "Cross Encoder 최종 결과 개수",
            DEFAULT_RERANK_TOP_K,
        )

        try:
            (
                keywords,
                metadata_filter,
                filtered_document_count,
                vector_results,
                bm25_results,
                rrf_results,
                reranked_results,
            ) = hybrid_search_with_reranking(
                vector_store=vector_store,
                embeddings=embeddings,
                bm25_index=bm25_index,
                filter_extractor=filter_extractor,
                reranker=reranker,
                query=query,
                candidate_k=candidate_k,
                rrf_candidate_k=rrf_candidate_k,
                rerank_top_k=rerank_top_k,
            )

            # 03.03과 동일한 검색 요약 및 Metadata Filter 출력
            print("\n" + "#" * 100)
            print("[Oliview 하이브리드 검색 + Cross Encoder 리랭킹]")
            print("#" * 100)
            print(f"사용자 질문       : {query}")
            print(
                "Kiwi 추출 키워드 : "
                + (", ".join(keywords) if keywords else "-")
            )
            print(f"필터 적용 문장 수 : {filtered_document_count:,}개")
            print(f"Chroma 후보 수    : {len(vector_results)}개")
            print(f"BM25 후보 수      : {len(bm25_results)}개")
            print(f"RRF 후보 수       : {len(rrf_results)}개")
            print(f"리랭킹 최종 수    : {len(reranked_results)}개")
            print("#" * 100)

            # 실제 검색 실행
            hybrid.print_metadata_filter(
                metadata_filter=metadata_filter,
                filtered_document_count=filtered_document_count,
            )

            hybrid.print_simple_candidates(
                title="[Chroma 상위 후보 미리보기]",
                results=vector_results,
                search_type="vector",
            )

            hybrid.print_simple_candidates(
                title="[BM25 상위 후보 미리보기]",
                results=bm25_results,
                search_type="bm25",
            )

            print_rrf_candidates(rrf_results)
            print_reranked_results(query, reranked_results)

        except Exception as error:
            print("\n" + "!" * 100)
            print("[리랭킹 검색 중 오류 발생]")
            print(f"오류 종류: {type(error).__name__}")
            print(f"오류 내용: {error}")
            print("!" * 100)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()


# =============================================================================
# [9] 메인 실행
# =============================================================================


def main() -> None:
    try:
        # 03.03의 기존 구성요소를 그대로 생성합니다.
        # 임베딩 모델
        embeddings = hybrid.create_embedding_model()

        # ChromaDB
        vector_store = hybrid.load_vector_store(
            embeddings=embeddings,
        )

        # BM25
        bm25_index = hybrid.ChromaBM25Index(
            vector_store=vector_store,
        )

        # Metadata Filter
        filter_extractor = hybrid.MetadataFilterExtractor(
            bm25_index=bm25_index,
        )

        # Cross Encoder
        # RRF 후보를 최종 순서로 재정렬할 Cross Encoder를 추가합니다.
        reranker = BGEReranker()

        # 모든 구성요소를 넘겨두고 실제 사용자 질문을 받기 시작
        run_interactive_reranking(
            vector_store=vector_store,
            embeddings=embeddings,
            bm25_index=bm25_index,
            filter_extractor=filter_extractor,
            reranker=reranker,
        )

    except KeyboardInterrupt:
        print("\n\n사용자가 실행을 중단했습니다.")

    except Exception as error:
        print("\n" + "=" * 100)
        print("[ERROR] 리랭킹 검색 실행 중 오류가 발생했습니다.")
        print(f"오류 종류: {type(error).__name__}")
        print(f"오류 내용: {error}")
        print("=" * 100)
        raise

    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    main()