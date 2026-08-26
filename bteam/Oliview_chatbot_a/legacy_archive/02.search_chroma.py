# uv run python 02.search_chroma.py

# 질문
#    ↓
# 벡터 검색 테스트


"""
Oliview Chroma DB 기본 벡터 검색

전체 흐름
------------------------------------------------------------
1. 프로젝트 내부 BGE-M3 임베딩 모델 불러오기
2. 기존 Chroma DB 불러오기
3. 사용자 질문 입력
4. 질문을 BGE-M3로 임베딩
5. Chroma DB에서 의미가 유사한 리뷰 문장 검색
6. 상위 K개 결과와 metadata 출력

중요
------------------------------------------------------------
- 사용자 질문은 짧기 때문에 별도로 청킹하지 않습니다.
- 질문 전체를 하나의 벡터로 임베딩합니다.
- 01.build_chroma_db.py에서 사용한 임베딩 모델 및 설정과
  동일한 설정을 사용해야 합니다.
"""

import os
import sys

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


# ============================================================
# [1] 프로젝트 최상위 경로 찾기
# ============================================================

def get_project_root() -> str:
    """
    현재 파일의 위치를 기준으로 프로젝트 최상위 폴더를 찾습니다.

    현재 폴더 또는 부모 폴더에 아래 항목 중 하나가 있으면
    프로젝트 최상위 폴더로 판단합니다.

    - pyproject.toml
    - common
    - evaluator
    """

    current = os.path.abspath(os.path.dirname(__file__))

    if (
        os.path.exists(os.path.join(current, "pyproject.toml"))
        or os.path.exists(os.path.join(current, "common"))
        or os.path.exists(os.path.join(current, "evaluator"))
    ):
        return current

    parent = os.path.abspath(
        os.path.join(current, "..")
    )

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


# ============================================================
# [2] 프로젝트 내부 모듈 불러오기
# ============================================================

from common.utils import get_bge_m3_device


load_dotenv(
    os.path.join(ROOT_DIR, ".env")
)


# ============================================================
# [3] 기본 설정
# ============================================================

# 프로젝트 내부 BGE-M3 모델 경로
LOCAL_MODEL_PATH = os.path.join(
    ROOT_DIR,
    "models",
    "embeddings",
    "bge-m3",
)

# Chroma DB 저장 경로
CHROMA_DB_PATH = os.path.join(
    ROOT_DIR,
    "chroma_db_oliview",
)

# 01.build_chroma_db.py에서 사용한 컬렉션명
COLLECTION_NAME = "oliview_review_sentences"

# 기본 검색 결과 개수
DEFAULT_TOP_K = 5

# 질문 임베딩 시 사용할 배치 크기
# 질문은 한 번에 하나이므로 큰 값이 필요하지 않습니다.
EMBEDDING_BATCH_SIZE = 16


# ============================================================
# [4] BGE-M3 로컬 모델 존재 여부 확인
# ============================================================

def is_local_model_ready(
    model_path: str,
) -> bool:
    """
    프로젝트 내부 BGE-M3 모델의 필수 파일이 존재하는지 확인합니다.
    """

    required_files = [
        os.path.join(model_path, "modules.json"),
        os.path.join(model_path, "config.json"),
    ]

    return all(
        os.path.isfile(path)
        for path in required_files
    )


# ============================================================
# [5] BGE-M3 임베딩 모델 생성
# ============================================================

def create_embedding_model():
    """
    BGE-M3 임베딩 객체를 생성합니다.
    서버 환경에서는 원격 HTTP 임베딩 API(8090)를 우선 사용합니다.
    """
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
            "01.build_chroma_db.py 실행이 완료되었는지 확인해주세요."
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
            # 01.build_chroma_db.py와 반드시 동일해야 합니다.
            "normalize_embeddings": True,
            "batch_size": EMBEDDING_BATCH_SIZE,
        },
    )

    print("[INFO] BGE-M3 임베딩 모델 준비 완료")

    return embeddings


# ============================================================
# [6] 기존 Chroma DB 불러오기
# ============================================================

def load_vector_store(
    embeddings: HuggingFaceEmbeddings,
) -> Chroma:
    """
    01.build_chroma_db.py에서 생성한 기존 Chroma DB를 불러옵니다.
    """

    if not os.path.isdir(CHROMA_DB_PATH):
        raise FileNotFoundError(
            "\nChroma DB 폴더를 찾지 못했습니다.\n"
            f"확인 경로: {CHROMA_DB_PATH}\n\n"
            "01.build_chroma_db.py 실행이 완료되었는지 확인해주세요."
        )

    chroma_sqlite_path = os.path.join(
        CHROMA_DB_PATH,
        "chroma.sqlite3",
    )

    if not os.path.isfile(chroma_sqlite_path):
        raise FileNotFoundError(
            "\nChroma DB의 chroma.sqlite3 파일을 찾지 못했습니다.\n"
            f"확인 경로: {chroma_sqlite_path}\n\n"
            "01.build_chroma_db.py가 아직 실행 중이거나 "
            "정상적으로 완료되지 않았을 수 있습니다."
        )

    print("\n" + "=" * 90)
    print("[Oliview Chroma DB 불러오기]")
    print("=" * 90)
    print(f"Chroma 경로 : {CHROMA_DB_PATH}")
    print(f"컬렉션명    : {COLLECTION_NAME}")

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DB_PATH,
        embedding_function=embeddings,
        collection_metadata={
            "hnsw:space": "cosine",
        },
    )

    stored_count = vector_store._collection.count()

    print(f"저장 문장 수: {stored_count:,}개")
    print("=" * 90)

    if stored_count == 0:
        raise RuntimeError(
            "Chroma 컬렉션에 저장된 문장이 없습니다. "
            "01.build_chroma_db.py 실행 결과를 확인해주세요."
        )

    return vector_store


# ============================================================
# [7] 안전한 metadata 출력값 만들기
# ============================================================

def get_metadata_value(
    metadata: dict,
    key: str,
    default: str = "-",
) -> str:
    """
    metadata에서 값을 가져옵니다.

    값이 없거나 빈 문자열이면 기본값을 반환합니다.
    """

    value = metadata.get(key)

    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return text


# ============================================================
# [8] 거리값을 보기 쉬운 유사도 값으로 변환
# ============================================================

def distance_to_similarity(
    distance: float,
) -> float:
    """
    Chroma cosine distance를 보기 쉬운 유사도 형태로 변환합니다.

    01에서 hnsw:space를 cosine으로 설정했으므로,
    기본적인 해석은 아래와 같습니다.

    similarity = 1 - distance

    - distance가 낮을수록 유사함
    - similarity가 높을수록 유사함

    데이터와 라이브러리 설정에 따라 similarity가
    음수가 될 수 있으므로 출력용으로만 사용합니다.
    """

    return 1.0 - float(distance)


# ============================================================
# [9] 검색 결과 출력
# ============================================================

def print_search_results(
    query: str,
    results: list,
) -> None:
    """
    Chroma 검색 결과를 순위별로 출력합니다.
    """

    print("\n" + "#" * 100)
    print("[Chroma 벡터 검색 결과]")
    print("#" * 100)
    print(f"검색 질문 : {query}")
    print(f"검색 결과 : {len(results)}개")
    print("#" * 100)

    if not results:
        print("\n검색 결과가 없습니다.")
        return

    for rank, (document, distance) in enumerate(
        results,
        start=1,
    ):
        metadata = document.metadata or {}
        sentence_text = document.page_content.strip()

        similarity = distance_to_similarity(distance)

        print("\n" + "=" * 100)
        print(f"[Rank {rank}]")
        print("=" * 100)

        # Chroma의 원래 검색 점수
        print(f"거리 점수     : {float(distance):.6f}")
        print(f"변환 유사도   : {similarity:.6f}")
        print(
            "점수 해석     : "
            "거리 점수는 낮을수록, 변환 유사도는 높을수록 관련성이 높습니다."
        )

        print("-" * 100)

        print(
            f"상품 ID       : "
            f"{get_metadata_value(metadata, 'product_id')}"
        )
        print(
            f"상품명        : "
            f"{get_metadata_value(metadata, 'product_name')}"
        )
        print(
            f"브랜드명      : "
            f"{get_metadata_value(metadata, 'brand_name')}"
        )
        print(
            f"분석 카테고리 : "
            f"{get_metadata_value(metadata, 'analysis_category_name')}"
        )
        print(
            f"상품 카테고리 : "
            f"{get_metadata_value(metadata, 'category_names')}"
        )
        print(
            f"속성          : "
            f"{get_metadata_value(metadata, 'attribute_name')}"
        )
        print(
            f"감성          : "
            f"{get_metadata_value(metadata, 'sentiment')}"
        )
        print(
            f"리뷰 작성일   : "
            f"{get_metadata_value(metadata, 'review_date')}"
        )

        print("-" * 100)
        print("[리뷰 문장]")
        print(sentence_text)
        print("=" * 100)


# ============================================================
# [10] Chroma 유사도 검색
# ============================================================

def search_chroma(
    vector_store: Chroma,
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> list:
    """
    사용자 질문을 임베딩하여 Chroma DB에서
    의미가 유사한 리뷰 문장을 검색합니다.

    반환값:
        [
            (Document, distance),
            (Document, distance),
            ...
        ]

    cosine distance는 낮을수록 질문과 리뷰 문장이 유사합니다.
    """

    cleaned_query = query.strip()

    if not cleaned_query:
        return []

    if top_k <= 0:
        raise ValueError(
            "top_k는 1 이상의 정수여야 합니다."
        )

    collection_count = vector_store._collection.count()

    # 저장된 문장 수보다 많은 결과를 요청하지 않도록 제한
    actual_top_k = min(
        top_k,
        collection_count,
    )

    results = vector_store.similarity_search_with_score(
        query=cleaned_query,
        k=actual_top_k,
    )

    return results


# ============================================================
# [11] 검색 결과 개수 입력
# ============================================================

def input_top_k() -> int:
    """
    사용자에게 검색 결과 개수를 입력받습니다.

    입력하지 않으면 DEFAULT_TOP_K를 사용합니다.
    """

    raw_value = input(
        f"검색 결과 개수 "
        f"(기본값 {DEFAULT_TOP_K}): "
    ).strip()

    if not raw_value:
        return DEFAULT_TOP_K

    try:
        top_k = int(raw_value)

    except ValueError:
        print(
            f"[WARNING] 숫자가 아니므로 기본값 "
            f"{DEFAULT_TOP_K}를 사용합니다."
        )
        return DEFAULT_TOP_K

    if top_k <= 0:
        print(
            f"[WARNING] 1 이상의 숫자가 아니므로 기본값 "
            f"{DEFAULT_TOP_K}를 사용합니다."
        )
        return DEFAULT_TOP_K

    return top_k


# ============================================================
# [12] 대화형 검색 실행
# ============================================================

def run_interactive_search(
    vector_store: Chroma,
) -> None:
    """
    사용자가 여러 질문을 연속으로 검색할 수 있도록
    대화형 검색을 실행합니다.

    종료 명령:
    - exit
    - quit
    - q
    - 종료
    """

    exit_commands = {
        "exit",
        "quit",
        "q",
        "종료",
    }

    print("\n" + "=" * 100)
    print("[Oliview Chroma 벡터 검색 준비 완료]")
    print("=" * 100)
    print("화장품 또는 리뷰와 관련된 질문을 입력해주세요.")
    print("종료하려면 exit, quit, q 또는 종료를 입력하세요.")
    print("=" * 100)

    while True:
        try:
            query = input(
                "\n질문을 입력하세요: "
            ).strip()

        except (EOFError, KeyboardInterrupt):
            print("\n\n[INFO] 검색을 종료합니다.")
            break

        if not query:
            print("[WARNING] 질문을 입력해주세요.")
            continue

        if query.lower() in exit_commands:
            print("[INFO] 검색을 종료합니다.")
            break

        top_k = input_top_k()

        print("\n[INFO] 질문을 임베딩하고 Chroma DB를 검색합니다.")

        try:
            results = search_chroma(
                vector_store=vector_store,
                query=query,
                top_k=top_k,
            )

            print_search_results(
                query=query,
                results=results,
            )

        except Exception as error:
            print("\n" + "=" * 100)
            print("[ERROR] 검색 중 오류가 발생했습니다.")
            print(f"오류 종류: {type(error).__name__}")
            print(f"오류 내용: {error}")
            print("=" * 100)


# ============================================================
# [13] 메인 실행
# ============================================================

def main() -> None:
    """
    임베딩 모델과 Chroma DB를 한 번만 불러온 후
    대화형 검색을 시작합니다.
    """

    try:
        embeddings = create_embedding_model()

        vector_store = load_vector_store(
            embeddings=embeddings,
        )

        run_interactive_search(
            vector_store=vector_store,
        )

    except KeyboardInterrupt:
        print("\n[WARNING] 사용자에 의해 실행이 중단되었습니다.")

    except Exception as error:
        print("\n" + "=" * 100)
        print("[ERROR] Chroma 검색 프로그램 실행 중 오류가 발생했습니다.")
        print(f"오류 종류: {type(error).__name__}")
        print(f"오류 내용: {error}")
        print("=" * 100)


if __name__ == "__main__":
    # Windows 콘솔에서 한글 출력 깨짐 방지
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(
                encoding="utf-8"
            )
            sys.stderr.reconfigure(
                encoding="utf-8"
            )
        except Exception:
            pass

    main()

                                                                                                                             
# ==========================================================================================                                   
# [BGE-M3 임베딩 모델 로드]                                                                                                    
# ==========================================================================================                                   
# 모델 경로 : C:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\models\embeddings\bge-m3                                   
# 사용 장치 : cpu                                                                                                              
# ==========================================================================================                                   
# Loading weights: 100%|█████████████████████████████████████████████████████████████████| 391/391 [00:00<00:00, 17765.35it/s] 
# [INFO] BGE-M3 임베딩 모델 준비 완료                                                                                          
                                                                                                                             
# ==========================================================================================                                   
# [Oliview Chroma DB 불러오기]                                                                                                 
# ==========================================================================================                                   
# Chroma 경로 : C:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\chroma_db_oliview                                        
# 컬렉션명    : oliview_review_sentences                                                                                       
# 저장 문장 수: 57,435개                                                                                                       
# ==========================================================================================                                   
                                                                                                                             
# ====================================================================================================                         
# [Oliview Chroma 벡터 검색 준비 완료]                                                                                         
# ====================================================================================================
# 화장품 또는 리뷰와 관련된 질문을 입력해주세요.
# 종료하려면 exit, quit, q 또는 종료를 입력하세요.
# ====================================================================================================

# 질문을 입력하세요: 촉촉한 썬크림 추천해주세요
# 검색 결과 개수 (기본값 5): 5

# [INFO] 질문을 임베딩하고 Chroma DB를 검색합니다.

# ####################################################################################################
# [Chroma 벡터 검색 결과]
# ####################################################################################################
# 검색 질문 : 촉촉한 썬크림 추천해주세요
# 검색 결과 : 5개
# ####################################################################################################

# ====================================================================================================
# [Rank 1]
# ====================================================================================================
# 거리 점수     : 0.201083
# 변환 유사도   : 0.798917
# 점수 해석     : 거리 점수는 낮을수록, 변환 유사도는 높을수록 관련성이 높습니다.
# ----------------------------------------------------------------------------------------------------
# 상품 ID       : 38
# 상품명        : 브링그린 대나무 히알루 수분 부스팅 크림 100ml (2입기획/단품)
# 브랜드명      : 브링그린
# 분석 카테고리 : 스킨케어
# 상품 카테고리 : 크림
# 속성          : 수분감
# 감성          : 긍정
# 리뷰 작성일   : 2025-12-25
# ----------------------------------------------------------------------------------------------------
# [리뷰 문장]
# 촉촉한 수분크림이에요
# ====================================================================================================

# ====================================================================================================
# [Rank 2]
# ====================================================================================================
# 거리 점수     : 0.220911
# 변환 유사도   : 0.779089
# 점수 해석     : 거리 점수는 낮을수록, 변환 유사도는 높을수록 관련성이 높습니다.
# ----------------------------------------------------------------------------------------------------
# 상품 ID       : 120
# 상품명        : [무찌PICK]식물나라 가벼운 수분 선 젤 60ml 단품/2입/대용량/트래블키트
# 브랜드명      : 식물나라
# 분석 카테고리 : 선케어
# 상품 카테고리 : 선크림
# 속성          : 자극성
# 감성          : 긍정
# 리뷰 작성일   : 2026-08-04
# ----------------------------------------------------------------------------------------------------
# [리뷰 문장]
# 순한 썬크림이에요.
# ====================================================================================================

# ====================================================================================================
# [Rank 3]
# ====================================================================================================
# 거리 점수     : 0.221599
# 변환 유사도   : 0.778401
# 점수 해석     : 거리 점수는 낮을수록, 변환 유사도는 높을수록 관련성이 높습니다.
# ----------------------------------------------------------------------------------------------------
# 상품 ID       : 46
# 상품명        : 차앤박(CNP) 프로폴리스 앰플 액티브 샷크림 1+1 기획(50ml+50ml)
# 브랜드명      : 차앤박
# 분석 카테고리 : 스킨케어
# 상품 카테고리 : 크림
# 속성          : 수분감
# 감성          : 중립
# 리뷰 작성일   : 2025-09-11
# ----------------------------------------------------------------------------------------------------
# [리뷰 문장]
# 수분크림보다는 조금 더 촉촉한 정도...?
# ====================================================================================================

# ====================================================================================================
# [Rank 4]
# ====================================================================================================
# 거리 점수     : 0.221637
# 변환 유사도   : 0.778363
# 점수 해석     : 거리 점수는 낮을수록, 변환 유사도는 높을수록 관련성이 높습니다.
# ----------------------------------------------------------------------------------------------------
# 상품 ID       : 42
# 상품명        : [쿨링/수분] 차앤박 아쿠아 수딩 크림 1+1 기획
# 브랜드명      : 차앤박
# 분석 카테고리 : 스킨케어
# 상품 카테고리 : 크림
# 속성          : 수분감
# 감성          : 긍정
# 리뷰 작성일   : 2025-05-01
# ----------------------------------------------------------------------------------------------------
# [리뷰 문장]
# 촉촉한 수분크림이예요.
# ====================================================================================================

# ====================================================================================================
# [Rank 5]
# ====================================================================================================
# 거리 점수     : 0.230642
# 변환 유사도   : 0.769358
# 점수 해석     : 거리 점수는 낮을수록, 변환 유사도는 높을수록 관련성이 높습니다.
# ----------------------------------------------------------------------------------------------------
# 상품 ID       : 44
# 상품명        : 헤라 하이드로 리플렉팅 마이크로 크림 50ml
# 브랜드명      : 헤라
# 분석 카테고리 : 스킨케어
# 상품 카테고리 : 크림
# 속성          : 수분감
# 감성          : 긍정
# 리뷰 작성일   : 2023-10-07
# ----------------------------------------------------------------------------------------------------
# [리뷰 문장]
# 촉촉함이 잘 느껴지는 수분크림으로
# ====================================================================================================

# 질문을 입력하세요: 