# uv run python 01.build_chroma_db.py

# ============================================================
# 핵심구조
# ============================================================

# MySQL 뷰 → 리뷰 문장 조회 (배치 단위로)
#              |
#              ▼
# 프로젝트 내부 BGE-M3 모델 준비
#              |
#              ▼
# 문장별 BGE-M3 임베딩 생성
#              |
#              ▼
# Chroma DB 저장(add_texts)
#              |
#              ▼
# 다음 배치 반복

# ============================================================
# Chroma DB 저장 구조
# ============================================================
#
# MySQL 뷰(vw_chroma_review_sentences)이용
#
# ChromaDB
# │
# ├─ 1. ID
# │   └─ sentence_id
# │
# ├─ 2. Document
# │   └─ sentence_text
# │
# ├─ 3. Embedding
# │   └─ sentence_text를 BGE-M3로 임베딩한 벡터
# │
# └─ 4. Metadata
#     ├─ product_id               (상품번호)
#     ├─ product_name             (상품명)
#     ├─ brand_name               (브랜드명)
#     ├─ analysis_category_name   (분석 카테고리명)
#     ├─ category_names           (소분류 카테고리명)
#     ├─ attribute_name           (속성이름)
#     ├─ sentiment                (감성분석 결과)
#     └─ review_date              (리뷰작성 날짜)
#
# MySQL 뷰에서 아래 검증용 컬럼도 함께 조회하지만,
# 현재 create_metadata()에는 포함하지 않으므로
# Chroma metadata에는 저장되지 않습니다.
#
# - brand_id
# - analysis_category_id
# - category_ids
#
# 
# ============================================================
# 코드 전체 흐름
# ============================================================
#
# 1) 01.build_chroma_db.py 실행
#         ↓
# 2) 프로젝트 최상위 폴더 찾기
#         ↓
# 3) .env 읽기
#         ↓
# 4) 기존 Chroma DB 삭제 여부 확인
#         ↓
# 5) MySQL 연결
#         ↓
# 6) 저장할 리뷰 문장 개수 확인
#         ↓
# 7) BGE-M3 모델 존재 여부 확인
#         ↓
# 8) 없으면 Hugging Face에서 다운로드
#         ↓
# 9) BGE-M3 임베딩 객체 생성
#         ↓
# 10) Chroma DB 객체 생성
#         ↓
# 11) MySQL에서 리뷰 문장 1,000개 조회
#         ↓
# 12) 빈 문장 제거
#         ↓
# 13) 문장 + metadata 준비
#         ↓
# 14) BGE-M3로 벡터 변환
#         ↓
# 15) Chroma DB 저장
#         ↓
# 16) 다음 1,000개 조회 (sentence_id를 기준)
#         ↓
# 17) 끝날 때까지 반복
#         ↓
# 18) 최종 Chroma 저장 개수 확인
#         ↓
# 19) MySQL 연결 종료

# ============================================================
# 코드 실행 후 생성되는 폴더
# ============================================================
# OLIVIEW_CHATBOT
# │
# ├── models
# │   └── embeddings
# │       └── bge-m3          ← ① BGE-M3 임베딩 모델
# │
# ├── chroma_db_oliview       ← ② Chroma 벡터 DB
# │
# ├── common
# ├── evaluator
# ├── 01.build_chroma_db.py
# └── ...


import os   # 프로젝트 폴더, 모델폴더, Chroma DB폴더 다룰때 사용 
import sys  # Python 실행환경 관련 - 프로젝트 폴더를 Python import경로에 추가, Windows인지 확인
from datetime import date, datetime  # MySQL에서 가져온 날짜 데이터를 확인하기 위해 사용
                                     # 리뷰날짜가 Python 날짜객체라면 Chroma metadata에 그대로 넣기보다는 문자열로 반환
from typing import Any # 타입힌트를 위한 것

from dotenv import load_dotenv                           # .env파일을 읽음
from huggingface_hub import snapshot_download            # Hugging Face에 있는 BAAI/bge-m3 모델을 통째로 프로젝트 폴더에 다운로드할 때 사용
from langchain_chroma import Chroma                      # Chroma 벡터 DB를 만들거나 불러오기 위한 class
from langchain_huggingface import HuggingFaceEmbeddings  # BGE-M3 모델을 LangChain에서 임베딩 모델로 사용할 수 있게 만들어줌


# ============================================================
# [1] 프로젝트 최상위 경로 찾기
# ============================================================

# 현재 01.build_chroma_db.py가 어디에 있든 최상위 폴더를 찾아주는 것
def get_project_root() -> str:
    """
    현재 파이썬 파일을 기준으로 프로젝트 최상위 폴더를 찾습니다.

    현재 폴더 또는 부모 폴더에 아래 항목이 있으면
    프로젝트 최상위 폴더로 판단합니다.

    - pyproject.toml
    - common
    - evaluator
    """

    # 1) 현재 실행중인 파일의 경로를 절대경로로 바꿈
    current = os.path.abspath(os.path.dirname(__file__))

    # 현재 폴더에 pyproject.toml, common, evaluator 중 하나가 존재하면
    # 프로젝트 최상위 폴더로 판단 후 현재 절대경로(current)반환
    if (
        os.path.exists(os.path.join(current, "pyproject.toml"))
        or os.path.exists(os.path.join(current, "common"))
        or os.path.exists(os.path.join(current, "evaluator"))
    ):
        return current

    # 2) 만약 현재 폴더가 프로젝트 최상위 폴더가 아니라면
    # 한 단계 위 부모 폴더를 구함
    parent = os.path.abspath(os.path.join(current, ".."))

    # 부모 폴더(parent)에 pyproject.toml, common, evaluator 중 하나가 존재하면
    # 프로젝트 최상위 폴더로 판단 후 현재 절대경로 반환
    if (
        os.path.exists(os.path.join(parent, "pyproject.toml"))
        or os.path.exists(os.path.join(parent, "common"))
        or os.path.exists(os.path.join(parent, "evaluator"))
    ):
        return parent

    # 3) 둘다 아니라면 현재 폴더(current)를 그냥 사용
    return current

# 4) ROOT_DIR 설정
# get_project_root함수를 실행해서 프로젝트 최상위 경로를 지정
ROOT_DIR = get_project_root()

# Python이 모듈을 찾을 때 ROOT_DIR도 검색하도록 등록
# 이걸 해야 프로젝트 내부 파일을 안정적으로 import가능
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# ============================================================
# [2] 프로젝트 내부 모듈 불러오기
# ============================================================

from common.db_manager import get_connection # get_connection : MySQL에 연결하는 함수
                                             # .env에 있는 DB정보 읽기 -> MySQL 연결 -> connection 반환

from common.utils import get_bge_m3_device, safe_remove_directory
# get_bge_m3_device : BGM-M3를 어디에서 실행할지 결정
                    # 예 : GPU 사용 가능 → cuda, 
                    #      없음 → cpu
                    # 현재코드에선 cpu 사용함

# safe_remove_directory : 폴더를 안전하게 삭제하는 함수
                        # 현재코드에선 폴더나 불완전하게 다운로드된 모델폴더를 지울 때 사용함

# .env 읽기
# ROOT_DIR/.env 파일을 읽음
load_dotenv(os.path.join(ROOT_DIR, ".env"))


# ============================================================
# [3] 기본 설정
# ============================================================

# 1) Chroma DB를 만들때, 원본 데이터로 사용할 MySQL View
VIEW_NAME = "vw_chroma_review_sentences"

# 2) 사용할 Hugging Face 모델 저장소 이름
# 리뷰 문장을 벡터로 변환하는 모델 = BGE-M3
EMBEDDING_MODEL_REPO_ID = "BAAI/bge-m3"

# 프로젝트 내부 모델 저장경로
# models/embeddings/bge-m3
LOCAL_MODEL_RELATIVE_PATH = os.path.join(
    "models",
    "embeddings",
    "bge-m3",
)

# 상대경로를 실제 절대경로로 바꿈
LOCAL_MODEL_PATH = os.path.join(
    ROOT_DIR,
    LOCAL_MODEL_RELATIVE_PATH,
)

# 3) 프로젝트 내부 Chroma DB 저장경로
CHROMA_DB_DIR_NAME = "chroma_db_oliview"

# 상대경로를 실제 절대경로로 바꿈
CHROMA_DB_PATH = os.path.join(
    ROOT_DIR,
    CHROMA_DB_DIR_NAME,
)

# 4) Chroma 컬렉션명
# Chroma 안에서도 데이터를 collection 단위로 관리
    # MySQL
    #  └ DB
    #     └ Table
    # Chroma
    #  └ DB
    #     └ Collection
COLLECTION_NAME = "oliview_review_sentences"

# 5) MySQL에서 한 번에 가져올 문장 수
DB_BATCH_SIZE = 1000

# 6) BGE-M3가 한 번에 임베딩할 문장 수
# 메모리 부족 시 16 → 8로 줄이면 됩니다.
EMBEDDING_BATCH_SIZE = 16

# 7) Chroma DB 재구축 여부
# True:
# 기존 Chroma DB를 지운 뒤 처음부터 재구축
#
# False:
# 기존 DB를 유지
REBUILD_EXISTING_DB = True

# 8) 임베딩 대상 문장 수 제한
# None = 1000 -> 처음 1,000개 문장만 임베딩하여  Chroma DB 구축
# None = None -> 전체문장을 임베딩하여 Chroma DB 구축
TEST_LIMIT: int | None = None


# ============================================================
# [4] 프로젝트 내부 BGE-M3 모델 준비
# ============================================================

# 1) is_local_model_ready() : BGE-M3 모델이 로컬에 있는지 검사
def is_local_model_ready(model_path: str) -> bool:
    """
    로컬에 BGE-M3 모델의 필수 파일이 존재하는지 확인합니다.
    """

    # models > bge-m3 폴더에 modules.json, config.json이 있는 지 확인
    required_files = [
        os.path.join(model_path, "modules.json"),
        os.path.join(model_path, "config.json"),
    ]

    # all() : 두 파일이 모두 존재하면 True, 하나라도 없으면 False 
    return all(os.path.isfile(path) for path in required_files)

# 2) ensure_local_embedding_model() : BGE-M3가 있으면 기존 걸 사용하고, 없으면 다운로드한다.
def ensure_local_embedding_model() -> str:
    """
    프로젝트 내부에 BGE-M3 모델이 없으면 다운로드하고,
    준비된 로컬 모델 경로를 반환합니다.
    """

    print("\n" + "=" * 90)
    print("[BGE-M3 로컬 모델 확인]")
    print("=" * 90)
    print(f"Hugging Face 모델 : {EMBEDDING_MODEL_REPO_ID}")
    print(f"로컬 모델 경로    : {LOCAL_MODEL_PATH}")

    # (1) 아까 만든함수로 BGE-M3 모델이 로컬에 있는지 검사
    if is_local_model_ready(LOCAL_MODEL_PATH):
        print("[INFO] 프로젝트 내부의 기존 BGE-M3 모델을 사용합니다.")
        print("=" * 90)
        # 있으면 다운로드하지 않고 바로 기존모델 사용
        return LOCAL_MODEL_PATH

    # (2) 반대로 폴더는 있는데 모델이 불완전하다면
    # 폴더가 존재하는지 확인하고 모델삭제
    if os.path.exists(LOCAL_MODEL_PATH):
        print("[WARNING] 불완전한 모델 폴더를 삭제합니다.")
        # 모델 삭제
        removed = safe_remove_directory(LOCAL_MODEL_PATH)

        # 모델 삭제에 실패하면, 오류를 발생시켜 구축을 중단 
        if removed is False and os.path.exists(LOCAL_MODEL_PATH):
            raise RuntimeError(
                f"불완전한 모델 폴더를 삭제하지 못했습니다: {LOCAL_MODEL_PATH}"
            )

    # (3) 모델을 저장할 상위폴더를 만듬
    os.makedirs(
        os.path.dirname(LOCAL_MODEL_PATH),
        exist_ok=True, # 폴더가 이미 있더라도 오류가 나지 않음
    )

    print("[INFO] BGE-M3 모델을 프로젝트 내부로 다운로드합니다.")
    print("[INFO] 최초 실행 시 다운로드에 시간이 걸릴 수 있습니다.")

    # (4) .env에서 Hugging Face token을 가져옴, 없으면 None
    hf_token = os.getenv("HF_TOKEN") or None

    # (5) 실제로 BGE-M3를 다운로드
    # models/embeddings/bge-m3에 BAAI/bge-m3 다운로드 
    snapshot_download(
        repo_id=EMBEDDING_MODEL_REPO_ID,
        local_dir=LOCAL_MODEL_PATH,
        token=hf_token,
    )

    # (6) 다운로드후 다시 BGE-M3 모델이 로컬에 있는지 검사
    if not is_local_model_ready(LOCAL_MODEL_PATH):
        raise RuntimeError( # 정상적으로 필요한 파일이 없으면 에러발생
            "BGE-M3 모델 다운로드 후 필수 파일을 찾지 못했습니다."
        )

    print("[INFO] BGE-M3 모델 다운로드 완료")
    print("=" * 90)

    # (7) 모델의 위치를 반환
    return LOCAL_MODEL_PATH


# ============================================================
# [5] Chroma metadata 값 정리
# ============================================================

# 1) Chroma metadata 값 정리
# Chrama metadata에는 아무 Python 객체를 넣을 수 있는 것이 아니므로
# 최종적으로 str | int | float | bool 형태로 맞춰줌
def normalize_metadata_value(
    value: Any,
) -> str | int | float | bool:
    """
    MySQL 값을 Chroma metadata가 지원하는 자료형으로 변환합니다.
    """

    # MySQL NULL이면 -> 빈 문자열로 변환
    if value is None:
        return ""

    # 날짜면 -> 문자열로 변환
    # 예) date(2026,8,7) -> "2026-08-07"
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    # 이미 Chroma에서 사용할 수 있는 형식이면 -> 그대로
    if isinstance(value, (str, int, float, bool)):
        return value

    # 그 외의 자료형 -> 문자열로 변환
    return str(value)


# 2) Metadata 만들기
# MySQL의 한 행을 받아서 -> Chroma metadata를 만듬
def create_metadata(
    row: dict[str, Any],
) -> dict[str, str | int | float | bool]:
    """
    MySQL 뷰의 한 행에서 Chroma metadata를 만듭니다.
    """

    return {
        # 상품번호
        "product_id": normalize_metadata_value(
            row["product_id"]
        ),
        # 상품명
        "product_name": normalize_metadata_value(
            row["product_name"]
        ),
        # 브랜드명
        "brand_name": normalize_metadata_value(
            row["brand_name"]
        ),
        # 분석 카테고리명
        "analysis_category_name": normalize_metadata_value(
            row["analysis_category_name"]
        ),
        # 소분류 카테고리명(level 3)
        "category_names": normalize_metadata_value(
            row["category_names"]
        ),
        # 속성명
        "attribute_name": normalize_metadata_value(
            row["attribute_name"]
        ),
        # 감성분석 결과
        "sentiment": normalize_metadata_value(
            row["sentiment"]
        ),
        # 리뷰 작성 날짜
        "review_date": normalize_metadata_value(
            row["review_date"]
        ),
    }

# Chroma 안의 데이터 예시
# ID = "100"

# Document = "커버력이 좋아요"

# Metadata = {
#     "product_id": 1234,
#     "product_name": "헤라 블랙 쿠션",
#     "brand_name": "헤라",
#     "analysis_category_name": "베이스메이크업",
#     "category_names": "...",
#     "attribute_name": "커버력",
#     "sentiment": "긍정",
#     "review_date": "2026-08-01"
# }

# ============================================================
# [6] MySQL 연결 보장
# ============================================================

# MySQL 연결이 살아있는지 확인
# BGM-M3임베딩이 오래걸려 그 사이 MySQL 연결이 끊어질 수 있기에 확인
# 임베딩 시간이 길더라도 비교적 안전하게 다음배치로 넘어갈 수 있음
def ensure_mysql_connection(connection):
    """
    MySQL 연결이 살아 있는지 확인합니다.

    임베딩 처리 중 연결이 끊어졌다면 자동으로 재연결하고
    새 연결 객체를 반환합니다.
    """

    # 아예 연결객체가 없으면 -> 새로 연결
    if connection is None:
        return get_connection()

    try:
        # MySQL 연결이 살아있는지 확인 후 -> 필요하면 재연결, 정상이면 기존연결 사용
        connection.ping(reconnect=True)
        return connection

    except Exception: # 오류발생시
        try: 
            connection.close()  # 기존연결 닫음
        except Exception:
            pass

        print("[WARNING] MySQL 연결이 끊겨 새로 연결합니다.")
        # 새 연결 만듬
        return get_connection()


# ============================================================
# [7] 저장 대상 전체 문장 수 조회
# ============================================================

# 저장할 문장 총 개수 가져오기
def get_total_sentence_count(connection) -> int:
    """
    실제 저장 대상 문장 수를 반환합니다.

    TEST_LIMIT가 None이면 뷰 전체 개수,
    숫자이면 전체 개수와 TEST_LIMIT 중 작은 값을 반환합니다.
    """

    # DB연결 상태 확인
    connection = ensure_mysql_connection(connection)

    # TEST_LIMIT이 None이면
    if TEST_LIMIT is None:
        # View의 전체 행 수를 셈
        sql = f"""
            SELECT COUNT(*) AS total_count
            FROM {VIEW_NAME}
        """

        #  MySQL cursor를 염
        with connection.cursor() as cursor:
            cursor.execute(sql)         # SQL 실행
            result = cursor.fetchone()  # 결과 한 행을 가져옴 ->  {"total_count: 57435"}

        return int(result["total_count"]) # 57435를 반환

    # TEST_LIMIT 이 None이 아니면
    sql = f"""
        SELECT LEAST(COUNT(*), %s) AS total_count
        FROM {VIEW_NAME}
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (TEST_LIMIT,))
        result = cursor.fetchone()

    return int(result["total_count"])


# ============================================================
# [8] MySQL 문장 배치 조회
# ============================================================

# MySQL에서 리뷰문장 1배치 가져오기
def fetch_sentence_batch(
    connection,
    last_sentence_id: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    """
    마지막으로 처리한 sentence_id보다 큰 문장을
    batch_size개만 조회합니다.

    조회가 끝나면 with문에 의해 커서가 즉시 닫힙니다.
    따라서 임베딩 처리 중 MySQL 서버 사이드 커서를
    오래 열어두지 않습니다.
    """

    sql = f"""
        SELECT
            sentence_id,
            sentence_text,

            product_id,
            product_name,

            brand_id,
            brand_name,

            analysis_category_id,
            analysis_category_name,

            category_ids,
            category_names,

            attribute_name,
            sentiment,
            review_date

        FROM {VIEW_NAME}

        WHERE sentence_id > %s

        ORDER BY sentence_id

        LIMIT %s
    """

    # cursor를 열고
    with connection.cursor() as cursor:
        # SQL을 실행
        cursor.execute(
            sql,
            (
                last_sentence_id,
                batch_size,
            ),
        )

        # 해당 배치의 데이터를 전부 가져옴
        rows = cursor.fetchall()

    return rows


# ============================================================
# [9] BGE-M3 임베딩 모델 생성
# ============================================================

# BGE-M3 임베딩 객체 생성
def create_embedding_model() -> HuggingFaceEmbeddings:
    """
    프로젝트 내부 BGE-M3 모델로 임베딩 객체를 생성합니다.
    """
    # 모델이 있나 확인하고 없으면 다운로드
    model_path = ensure_local_embedding_model()
    # CPU/GPU 중 어디서 실행할지 결정
    device = get_bge_m3_device()

    print("\n" + "=" * 90)
    print("[BGE-M3 임베딩 모델 로드]")
    print("=" * 90)
    print(f"모델 경로       : {model_path}")
    print(f"사용 장치       : {device}")
    print(f"임베딩 배치 크기: {EMBEDDING_BATCH_SIZE}")

    # 로컬에 저장된 BGE-M3모델을 HuggingFace 임베딩 객체로 만듬
    embeddings = HuggingFaceEmbeddings(
        model_name=model_path,
        model_kwargs={
            "device": device,
            "local_files_only": True, # 인더텟에서 모델을 다시 찾지말고, 로컬모델만 사용하라는 의미
        },
        encode_kwargs={
            "normalize_embeddings": True, # 생성된 임베딩 벡터의 크기를 정규화
            "batch_size": EMBEDDING_BATCH_SIZE,
        },
    )

    print("[INFO] BGE-M3 임베딩 모델 준비 완료")
    print("=" * 90)

    # 완성된 임베딩객체를 반환
    return embeddings


# ============================================================
# [10] Chroma DB 객체 생성
# ============================================================

def create_vector_store(
    db_path: str,
    embeddings: HuggingFaceEmbeddings,
) -> Chroma:
    """
    Chroma DB 객체를 생성하거나 기존 DB를 불러옵니다.
    """

    return Chroma(
        collection_name=COLLECTION_NAME,  # collection 이름 = oliview_review_sentences
        persist_directory=db_path,        # DB를 지정된 폴더에 저장 -> chroma_db_oliview폴더에 실제 DB가 생성됨
        embedding_function=embeddings,    # 문장이 들어오면 BGE-M3모델을 사용해 벡터로 바꾸라고 지정
        collection_metadata={
            "hnsw:space": "cosine"        # 벡터간 유사도 비교시, cosine기준을 사용   
        },
    )


# ============================================================
# [11] MySQL 뷰 → Chroma DB 구축
# ============================================================

def build_chroma_db(
    db_path: str | None = None,          # Chroma를 어디에 만들지
    batch_size: int = DB_BATCH_SIZE,     # MySQL에서 몇개씩 가져올지
    rebuild: bool = REBUILD_EXISTING_DB, # 기존 DB를 삭제하고 다시 만들지
) -> Chroma | None:
    """
    vw_chroma_review_sentences의 리뷰 문장을 읽어
    Chroma DB를 구축합니다.

    MySQL 연결 끊김 방지를 위해:
    - 배치 조회 때만 커서를 엽니다.
    - 조회가 끝나면 커서를 바로 닫습니다.
    - 임베딩 후 다음 배치 조회 전에 ping(reconnect=True)을 실행합니다.
    """

    # 경로를 따로 전달하지 않았다면 기본경로 사용
    if db_path is None:
        db_path = CHROMA_DB_PATH

    # 전달된 경로가 상대경로라면 -> 프로젝트 루트 기준 절대경로로 만듬
    elif not os.path.isabs(db_path):
        db_path = os.path.join(
            ROOT_DIR,
            db_path,
        )

    print("\n" + "=" * 90)
    print("[Oliview Chroma DB 구축 시작]")
    print("=" * 90)
    print(f"MySQL 뷰          : {VIEW_NAME}")
    print(f"로컬 모델 경로    : {LOCAL_MODEL_PATH}")
    print(f"Chroma 저장 경로  : {db_path}")
    print(f"컬렉션명          : {COLLECTION_NAME}")
    print(f"MySQL 배치 크기   : {batch_size:,}개")
    print(f"임베딩 배치 크기  : {EMBEDDING_BATCH_SIZE}개")
    print(f"기존 DB 재구축    : {rebuild}")
    print(f"테스트 제한       : {TEST_LIMIT}")
    print("=" * 90)

    # connection 초기화, 아직 MySQL에 연결하지 않았다는 뜻
    connection = None

    try:
        # ----------------------------------------------------
        # 1. 기존 Chroma DB 처리
        # ----------------------------------------------------

        # 기존 Chroma 폴더가 있다면 -> 삭제
        if rebuild and os.path.exists(db_path):
            print("\n[INFO] 기존 Chroma DB 폴더를 삭제합니다.")

            removed = safe_remove_directory(db_path) # Chroma 폴더 삭제

            # Chroma 폴더 삭제 실패시 -> 중단
            if removed is False and os.path.exists(db_path):
                raise RuntimeError(
                    f"기존 Chroma DB 폴더를 삭제하지 못했습니다: {db_path}"
                )

        # ----------------------------------------------------
        # 2. MySQL 연결
        # ----------------------------------------------------

        print("\n[INFO] MySQL DB에 연결합니다.")

        # common.db.manager에 있는 함수를 이용해 DB에 연결
        # 이 명령 이후 connection.cursor()를 사용할 수 있게됨
        connection = get_connection() 

        print("[INFO] MySQL DB 연결 완료")

        # ----------------------------------------------------
        # 3. 전체 저장 대상 개수 확인
        # ----------------------------------------------------

        total_count = get_total_sentence_count(connection)

        print(f"[INFO] 전체 저장 대상 문장 수: {total_count:,}개")

        if total_count == 0:
            print("[WARNING] 뷰에 저장할 문장이 없습니다.")
            return None

        # ----------------------------------------------------
        # 4. BGE-M3 모델 준비
        # ----------------------------------------------------

        embeddings = create_embedding_model()

        # ----------------------------------------------------
        # 5. Chroma DB 객체 생성
        # ----------------------------------------------------

        # BEM-M3와 연결된 Chroma 객체를 만듬
        vector_store = create_vector_store(
            db_path=db_path,
            embeddings=embeddings,
        )

        # ----------------------------------------------------
        # 6. 진행 상태 초기화
        # ----------------------------------------------------

        saved_count = 0    # Chroma에 실제 저장한 개수
        skipped_count = 0  # 빈 문장이라 제외한 개수
        batch_number = 0   # 몇번째 batch인지

        # 다음 SQL 조회 기준이 되는 마지막 문장 ID
        # 첫 실행은 0부터 시작
        last_sentence_id = 0

        # ----------------------------------------------------
        # 7. 배치 단위 조회·임베딩·저장
        # ----------------------------------------------------

        # 전체 데이터를 처리할 때까지 반복
        while saved_count + skipped_count < total_count:
            # 테스트 제한까지 남은 개수
            remaining_count = (
                total_count - saved_count - skipped_count
            )

            # 기본 batch가 1000이여도 마지막에는 남은 수(예 435개)만 가져오게 함
            current_batch_size = min(
                batch_size,
                remaining_count,
            )

            # 임베딩 처리 중 연결이 끊겼을 수 있으므로 
            # DB연결 다시 확인
            connection = ensure_mysql_connection(connection)

            # 이번 배치만 조회하고 커서를 즉시 닫음
            rows = fetch_sentence_batch(
                connection=connection,
                last_sentence_id=last_sentence_id,
                batch_size=current_batch_size,
            )

            # 어 이상 데이터가 없으면 반복 종료
            if not rows:
                break

            batch_number += 1

            # Chroma에 넣을 3가지 리스트
            ids: list[str] = []
            texts: list[str] = []
            metadatas: list[
                dict[str, str | int | float | bool]
            ] = []

            # MySQL 행 하나씩 처리
            for row in rows:
                # 조회 위치는 빈 문장 여부와 관계없이 계속 앞으로 이동
                # 현재 처리 중인 sentence_id를 기억
                last_sentence_id = int(
                    row["sentence_id"]
                )

                # 문장내용 정리 : Null을 빈 문자열로 안전하게 변환
                sentence_text = str(           # 2) 문자열로 변환
                    row["sentence_text"] or "" # 1) 문장이 Null이면 ""로 바꿈
                ).strip()                      # 3) 앞뒤 공백을 제거

                # NULL, 빈 문자열, 공백뿐인 문장은 ChromaDB 저장에서 제외
                if not sentence_text:
                    skipped_count += 1
                    continue

                # ID / text / metadata 쌓기
                ids.append(
                    str(row["sentence_id"])
                )
                texts.append(sentence_text)
                metadatas.append(
                    create_metadata(row)
                )

            # ** 실제 BGE-M3 임베딩 + Chroma 저장
            if texts: # 저장할 문장이 하나라도 있으면 실행

                
                # add_texts 내부에서:
                # text → HuggingFaceEmbeddings → BGE-M3 임베딩 → 벡터생성 →  Chroma 저장
                vector_store.add_texts(
                    texts=texts,
                    metadatas=metadatas,
                    ids=ids,
                )

                saved_count += len(texts)

            # 진행률 계산
            processed_count = (
                saved_count + skipped_count  # 저장개수 + 스킵개수
            )

            # 백분율 계산
            progress = (
                processed_count / total_count * 100
            )

            # 진행로그 출력
            print(
                f"[배치 {batch_number:>3}] "
                f"처리 {processed_count:>7,}/{total_count:,}개 | "
                f"저장 {saved_count:>7,}개 | "
                f"제외 {skipped_count:>4,}개 "
                f"({progress:6.2f}%)"
            )

        # ----------------------------------------------------
        # 8. 최종 저장 결과 확인
        # ----------------------------------------------------

        # 실제로 Chroma collection에 몇 개가 들어갔는지 확인
        # saved_count : python 코드가 "몇개 저장했다고 생각하는지"
        # chroma_count : Chroma가 "실제로 DB안에 몇 개 들어있는지"를 셈
        chroma_count = (
            vector_store._collection.count()
        )

        print("\n" + "=" * 90)
        print("[Oliview Chroma DB 구축 완료]")
        print("=" * 90)
        print(f"전체 대상 문장 수 : {total_count:,}개")
        print(f"이번 저장 문장 수 : {saved_count:,}개")
        print(f"빈 문장 제외 수   : {skipped_count:,}개")
        print(f"Chroma 전체 개수  : {chroma_count:,}개")
        print(f"마지막 문장 ID    : {last_sentence_id:,}")
        print(f"모델 저장 경로    : {LOCAL_MODEL_PATH}")
        print(f"Chroma 저장 경로  : {db_path}")
        print(f"컬렉션명          : {COLLECTION_NAME}")
        print("=" * 90)

        # 정상완료되면 만들어진 Chroma 객체를 반환
        return vector_store

    # 사용자가 Cntrl + C로 중단했을 떄
    except KeyboardInterrupt:
        print(
            "\n[WARNING] 사용자에 의해 "
            "Chroma DB 구축이 중단되었습니다."
        )
        return None

    # 그 외 오류처리
    except Exception as error:
        print("\n" + "=" * 90)
        print("[ERROR] Chroma DB 구축 중 오류가 발생했습니다.")
        print(f"오류 종류: {type(error).__name__}")
        print(f"오류 내용: {error}")
        print("=" * 90)
        return None

    finally: # MySQL 반드시 닫기
        if connection is not None: # MySQL 연결이 만들어졌다면
            try:
                connection.close() # 연결을 종료
                print("[INFO] MySQL 연결을 종료했습니다.")
            except Exception:
                pass


# ============================================================
# [12] 메인 실행
# ============================================================

if __name__ == "__main__":
    if sys.platform == "win32": # 현재 운영체제가 Windows인지 확인
        try:
            sys.stdout.reconfigure( # Windows 터미널에서 한글출력 깨짐방지, stdout을 UTF-8로 맞줌
                encoding="utf-8" 
            )
        except Exception:
            pass

    build_chroma_db(
        db_path=CHROMA_DB_PATH,
        batch_size=DB_BATCH_SIZE,
        rebuild=REBUILD_EXISTING_DB,
    )
'''
if __name__ == "__main__"
        │
        ▼
build_chroma_db()
        │
        ├─ 기존 Chroma 삭제
        │
        ├─ get_connection()
        │      └─ MySQL 연결
        │
        ├─ get_total_sentence_count()
        │      └─ 57,435개 확인
        │
        ├─ create_embedding_model()
        │      │
        │      ├─ ensure_local_embedding_model()
        │      │      ├─ is_local_model_ready()
        │      │      └─ 없으면 snapshot_download()
        │      │
        │      └─ HuggingFaceEmbeddings(BGE-M3)
        │
        ├─ create_vector_store()
        │      └─ Chroma + BGE-M3 연결
        │
        └─ while 반복
               │
               ├─ ensure_mysql_connection()
               │
               ├─ fetch_sentence_batch()
               │      └─ MySQL 1,000개
               │
               ├─ for row in rows
               │      ├─ sentence_text 정리
               │      ├─ ID 준비
               │      └─ create_metadata()
               │
               └─ vector_store.add_texts()
                      │
                      ├─ BGE-M3 임베딩
                      │
                      └─ Chroma 저장
'''
                                                                                      
# (.venv) C:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot>c:/Users/MYCOM/Desktop/O
                                                                                      
# ======================================================================================
# [Oliview Chroma DB 구축 시작]                                                         
# ======================================================================================
# MySQL 뷰          : vw_chroma_review_sentences                                        
# 로컬 모델 경로    : c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\models\embed
# Chroma 저장 경로  : c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\chroma_db_ol
# 컬렉션명          : oliview_review_sentences                                          
# MySQL 배치 크기   : 1,000개                                                           
# 임베딩 배치 크기  : 16개                                                              
# 기존 DB 재구축    : True                                                              
# 테스트 제한       : None                                                              
# ======================================================================================
                                                                                      
# [INFO] 기존 Chroma DB 폴더를 삭제합니다.                                              
# [INFO] 기존 폴더 삭제 완료: c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\chro
                                                                                      
# [INFO] MySQL DB에 연결합니다.                                                         
# [INFO] MySQL DB 연결 완료                                                             
# c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\01.build_chroma_db.py:335: Depre
#   connection.ping(reconnect=True)                                                     
# [INFO] 전체 저장 대상 문장 수: 57,435개                                               
                                                                                      
# ======================================================================================
# [BGE-M3 로컬 모델 확인]                                                               
# ======================================================================================
# Hugging Face 모델 : BAAI/bge-m3                                                       
# 로컬 모델 경로    : c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\models\embed
# [INFO] 프로젝트 내부의 기존 BGE-M3 모델을 사용합니다.                                 
# ======================================================================================
# [INFO] CPU 사용                                                                       
                                                                                      
# ======================================================================================
# [BGE-M3 임베딩 모델 로드]                                                             
# ======================================================================================
# 모델 경로       : c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\models\embeddi
# 사용 장치       : cpu                                                                 
# 임베딩 배치 크기: 16                                                                  
# Loading weights: 100%|████████████████████████████████████████████████████████████████
# [INFO] BGE-M3 임베딩 모델 준비 완료                                                   
# ======================================================================================
# c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\01.build_chroma_db.py:335: Depre
#   connection.ping(reconnect=True)
# [배치   1] 처리   1,000/57,435개 | 저장   1,000개 | 제외    0개 (  1.74%)
# [배치   2] 처리   2,000/57,435개 | 저장   2,000개 | 제외    0개 (  3.48%)
# [배치   3] 처리   3,000/57,435개 | 저장   3,000개 | 제외    0개 (  5.22%)
# [배치   4] 처리   4,000/57,435개 | 저장   4,000개 | 제외    0개 (  6.96%)
# [배치   5] 처리   5,000/57,435개 | 저장   5,000개 | 제외    0개 (  8.71%)
# [배치   6] 처리   6,000/57,435개 | 저장   6,000개 | 제외    0개 ( 10.45%)
# [배치   7] 처리   7,000/57,435개 | 저장   7,000개 | 제외    0개 ( 12.19%)
# [배치   8] 처리   8,000/57,435개 | 저장   8,000개 | 제외    0개 ( 13.93%)
# [배치   9] 처리   9,000/57,435개 | 저장   9,000개 | 제외    0개 ( 15.67%)
# [배치  10] 처리  10,000/57,435개 | 저장  10,000개 | 제외    0개 ( 17.41%)
# [배치  11] 처리  11,000/57,435개 | 저장  11,000개 | 제외    0개 ( 19.15%)
# [배치  12] 처리  12,000/57,435개 | 저장  12,000개 | 제외    0개 ( 20.89%)
# [배치  13] 처리  13,000/57,435개 | 저장  13,000개 | 제외    0개 ( 22.63%)
# [배치  14] 처리  14,000/57,435개 | 저장  14,000개 | 제외    0개 ( 24.38%)
# [배치  15] 처리  15,000/57,435개 | 저장  15,000개 | 제외    0개 ( 26.12%)
# [배치  16] 처리  16,000/57,435개 | 저장  16,000개 | 제외    0개 ( 27.86%)
# [배치  17] 처리  17,000/57,435개 | 저장  17,000개 | 제외    0개 ( 29.60%)
# [배치  18] 처리  18,000/57,435개 | 저장  18,000개 | 제외    0개 ( 31.34%)
# [배치  19] 처리  19,000/57,435개 | 저장  19,000개 | 제외    0개 ( 33.08%)
# [배치  20] 처리  20,000/57,435개 | 저장  20,000개 | 제외    0개 ( 34.82%)
# [배치  21] 처리  21,000/57,435개 | 저장  21,000개 | 제외    0개 ( 36.56%)
# [배치  22] 처리  22,000/57,435개 | 저장  22,000개 | 제외    0개 ( 38.30%)
# [배치  23] 처리  23,000/57,435개 | 저장  23,000개 | 제외    0개 ( 40.05%)
# [배치  24] 처리  24,000/57,435개 | 저장  24,000개 | 제외    0개 ( 41.79%)
# [배치  25] 처리  25,000/57,435개 | 저장  25,000개 | 제외    0개 ( 43.53%)
# [배치  26] 처리  26,000/57,435개 | 저장  26,000개 | 제외    0개 ( 45.27%)
# [배치  27] 처리  27,000/57,435개 | 저장  27,000개 | 제외    0개 ( 47.01%)
# [배치  28] 처리  28,000/57,435개 | 저장  28,000개 | 제외    0개 ( 48.75%)
# [배치  29] 처리  29,000/57,435개 | 저장  29,000개 | 제외    0개 ( 50.49%)
# [배치  30] 처리  30,000/57,435개 | 저장  30,000개 | 제외    0개 ( 52.23%)
# [배치  31] 처리  31,000/57,435개 | 저장  31,000개 | 제외    0개 ( 53.97%)
# [배치  32] 처리  32,000/57,435개 | 저장  32,000개 | 제외    0개 ( 55.72%)
# [배치  33] 처리  33,000/57,435개 | 저장  33,000개 | 제외    0개 ( 57.46%)
# [배치  34] 처리  34,000/57,435개 | 저장  34,000개 | 제외    0개 ( 59.20%)
# [배치  35] 처리  35,000/57,435개 | 저장  35,000개 | 제외    0개 ( 60.94%)
# [배치  36] 처리  36,000/57,435개 | 저장  36,000개 | 제외    0개 ( 62.68%)
# [배치  37] 처리  37,000/57,435개 | 저장  37,000개 | 제외    0개 ( 64.42%)
# [배치  38] 처리  38,000/57,435개 | 저장  38,000개 | 제외    0개 ( 66.16%)
# [배치  39] 처리  39,000/57,435개 | 저장  39,000개 | 제외    0개 ( 67.90%)
# [배치  40] 처리  40,000/57,435개 | 저장  40,000개 | 제외    0개 ( 69.64%)
# [배치  41] 처리  41,000/57,435개 | 저장  41,000개 | 제외    0개 ( 71.39%)
# [배치  42] 처리  42,000/57,435개 | 저장  42,000개 | 제외    0개 ( 73.13%)
# [배치  43] 처리  43,000/57,435개 | 저장  43,000개 | 제외    0개 ( 74.87%)
# [배치  44] 처리  44,000/57,435개 | 저장  44,000개 | 제외    0개 ( 76.61%)
# [배치  45] 처리  45,000/57,435개 | 저장  45,000개 | 제외    0개 ( 78.35%)
# [배치  46] 처리  46,000/57,435개 | 저장  46,000개 | 제외    0개 ( 80.09%)
# [배치  47] 처리  47,000/57,435개 | 저장  47,000개 | 제외    0개 ( 81.83%)
# [배치  48] 처리  48,000/57,435개 | 저장  48,000개 | 제외    0개 ( 83.57%)
# [배치  49] 처리  49,000/57,435개 | 저장  49,000개 | 제외    0개 ( 85.31%)
# [배치  50] 처리  50,000/57,435개 | 저장  50,000개 | 제외    0개 ( 87.05%)
# [배치  51] 처리  51,000/57,435개 | 저장  51,000개 | 제외    0개 ( 88.80%)
# [배치  52] 처리  52,000/57,435개 | 저장  52,000개 | 제외    0개 ( 90.54%)
# [배치  53] 처리  53,000/57,435개 | 저장  53,000개 | 제외    0개 ( 92.28%)
# [배치  54] 처리  54,000/57,435개 | 저장  54,000개 | 제외    0개 ( 94.02%)
# [배치  55] 처리  55,000/57,435개 | 저장  55,000개 | 제외    0개 ( 95.76%)
# [배치  56] 처리  56,000/57,435개 | 저장  56,000개 | 제외    0개 ( 97.50%)
# [배치  57] 처리  57,000/57,435개 | 저장  57,000개 | 제외    0개 ( 99.24%)
# [배치  58] 처리  57,435/57,435개 | 저장  57,435개 | 제외    0개 (100.00%)

# ==========================================================================================
# [Oliview Chroma DB 구축 완료]
# ==========================================================================================
# 전체 대상 문장 수 : 57,435개
# 이번 저장 문장 수 : 57,435개
# 빈 문장 제외 수   : 0개
# Chroma 전체 개수  : 57,435개
# 마지막 문장 ID    : 57,435
# 모델 저장 경로    : c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\models\embeddings\bge-m3
# Chroma 저장 경로  : c:\Users\MYCOM\Desktop\OliviewProject\Oliview_chatbot\chroma_db_oliview컬렉션명          : oliview_review_sentences
# ==========================================================================================
# [INFO] MySQL 연결을 종료했습니다.