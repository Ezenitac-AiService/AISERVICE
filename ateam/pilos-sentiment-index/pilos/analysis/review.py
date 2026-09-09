from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import spmatrix
from sklearn.feature_extraction.text import TfidfVectorizer

from pilos.analysis.daily_dataset import (
    MARKET_CLOSE_TIME,
    iter_daily_documents,
)
from pilos.analysis.vectorizer import (
    create_tfidf_vectorizer,
    tokens_to_tfidf_text,
)
from pilos.storage.jsonl import iter_jsonl_records
from pilos.storage.normalization import normalize_comment_datetime


# CLI :
#  uv run python -m pilos.analysis.review

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

INPUT_DIR = DATA_DIR / "tokenized"
INPUT_PATTERN = "*.jsonl"
INPUT_PATHS = tuple(
    sorted(INPUT_DIR.glob(INPUT_PATTERN))
)

REVIEW_DIR = DATA_DIR / "review"

DAILY_METADATA_REVIEW_PATH = (
    REVIEW_DIR
    / "daily_metadata_review.csv"
)

DAILY_FEATURE_REVIEW_PATH = (
    REVIEW_DIR
    / "daily_feature_review.csv"
)

DAILY_TFIDF_SCORE_REVIEW_PATH = (
    REVIEW_DIR
    / "daily_tfidf_score_review.csv"
)

DAILY_TOKEN_SAMPLE_REVIEW_PATH = (
    REVIEW_DIR
    / "daily_token_sample_review.csv"
)

NGRAM_RANGE = (1, 1)
MIN_DF = 5
MAX_DF = 0.95
MAX_FEATURES = None
SUBLINEAR_TF = True
LOWERCASE = True

TOP_N = 10
TOKEN_SAMPLE_PER_DAY = 5


def _save_csv(
    dataframe: pd.DataFrame,
    output_path: Path,
) -> None:
    """
    DataFrame을 분석 검증용 CSV로 저장한다.
    """
    # 저장경로에 폴더가 없다면 생성한다
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    # Excel에서도 한글이 깨지지 않도록 UTF-8 BOM을 포함하고,
    # DataFrame 인덱스는 검수 컬럼에 포함하지 않는다
    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )


def _create_feature_review_dataframe(
    vectorizer: TfidfVectorizer,
) -> pd.DataFrame:
    """
    학습된 TF-IDF 벡터라이저의 feature와 IDF를
    검수용 DataFrame으로 생성한다.
    """
    return pd.DataFrame(
        {
            "word": vectorizer.get_feature_names_out(),
            "idf": vectorizer.idf_,
        }
    )


def _create_tfidf_score_review_dataframe(
    metadata_df: pd.DataFrame,
    tfidf_matrix: spmatrix,
    feature_names: np.ndarray,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    각 문서의 메타데이터에 TF-IDF 점수가 높은 단어와 점수를 결합한다.
    """
    # 메타데이터는 종목 코드, 날짜 등 각 문서를 설명하는 부가 정보다.
    # matrix는 행렬을 뜻하며, tfidf_matrix는 TF-IDF 결과를 저장한 희소행렬이다.

    if top_n <= 0:
        raise ValueError("top_n은 1 이상이어야 합니다.")

    # 메타데이터의 각 행과 TF-IDF 행렬의 각 행은 같은 문서를 나타내야 한다.
    if len(metadata_df) != tfidf_matrix.shape[0]:
        raise ValueError(
            "메타데이터의 행 수와 TF-IDF 행렬의 행 수가 다릅니다."
        )

    # feature 이름을 열 번호로 일관되게 조회할 수 있도록 NumPy 배열로 변환한다.
    feature_names = np.asarray(feature_names)

    # TF-IDF 행렬의 각 열에는 대응하는 feature 이름이 하나씩 있어야 한다.
    if len(feature_names) != tfidf_matrix.shape[1]:
        raise ValueError(
            "feature 이름 수와 TF-IDF 행렬의 열 수가 다릅니다."
        )

    rows = []

    # TF-IDF 행렬의 각 행, 즉 각 문서를 순회한다.
    for row_index in range(tfidf_matrix.shape[0]):
        # 같은 행 번호에 있는 문서의 메타데이터와 TF-IDF 결과를 가져온다.
        metadata = metadata_df.iloc[row_index].to_dict()
        row = tfidf_matrix.getrow(row_index)

        # 현재 행에 저장된 feature 위치와 TF-IDF 점수를 가져온다.
        # 두 배열은 같은 위치의 값끼리 서로 대응한다.
        feature_indices = row.indices
        scores = row.data

        # 현재 문서에 남아 있는 feature가 없으면 결과를 생성하지 않는다.
        if scores.size == 0:
            continue

        # argsort는 오름차순 위치를 반환하므로 음수를 붙여
        # 점수가 높은 순서대로 scores의 자리 번호를 구한다.
        top_positions = np.argsort(-scores)[:top_n]

        # position은 feature_indices와 scores에서 조회할 자리 번호다.
        for rank, position in enumerate(
            top_positions,
            start=1,
        ):
            # feature_index는 feature_names에서 단어를 찾을 때 사용한다.
            feature_index = feature_indices[position]

            rows.append(
                {
                    **metadata,
                    "rank": rank,
                    "word": feature_names[feature_index],
                    "score": float(scores[position]),
                }
            )

    return pd.DataFrame(
        rows,
        columns=[
            *metadata_df.columns,
            "rank",
            "word",
            "score",
        ],
    )


def _iter_records_with_token_samples(
    records: Iterable[dict],
    token_sample_rows: list[dict],
    sample_counts: dict[tuple[str, date], int],
    sample_size: int,
) -> Iterator[dict]:
    """
    댓글 레코드를 그대로 전달하면서
    종목·날짜별 토큰화 검수 표본을 제한된 수만큼 수집한다.
    """
    for record in records:
        # 저장 입력의 시각을 분석 영역에 전달하기 전에 정규화한다.
        created_at = normalize_comment_datetime(
            record.get("created_at")
        )
        normalized_record = record.copy()
        normalized_record["created_at"] = created_at

        if (
            created_at is not None
            and created_at.time() < MARKET_CLOSE_TIME
        ):
            stock_code = str(record["stock_code"])
            model_date = created_at.date()
            sample_key = (
                stock_code,
                model_date,
            )
            current_count = sample_counts.get(
                sample_key,
                0,
            )

            # 전체 토큰화 결과를 복제하지 않고
            # 각 종목·날짜의 앞쪽 댓글만 정해진 수만큼 보관한다.
            if current_count < sample_size:
                kiwi_tokens = record.get(
                    "kiwi_tokens"
                )

                token_sample_rows.append(
                    {
                        "stock_code": stock_code,
                        "model_date": model_date,
                        "comment_id": record.get(
                            "comment_id"
                        ),
                        "created_at": created_at,
                        "text": record.get("text"),
                        "kiwi_tokens": kiwi_tokens,
                        "tfidf_text": tokens_to_tfidf_text(
                            kiwi_tokens
                        ),
                    }
                )
                sample_counts[sample_key] = (
                    current_count + 1
                )

        # 표본 수집 여부와 관계없이 정규화된 레코드를 일별 집계기로 전달한다.
        yield normalized_record


def _iter_daily_documents_from_paths(
    input_paths: tuple[Path, ...],
    token_sample_rows: list[dict],
    token_sample_size: int,
) -> Iterator[dict]:
    """
    입력 경로를 순회하며 토큰화 표본을 수집하고
    종목·날짜별 TF-IDF 입력 문서를 하나씩 반환한다.
    """
    sample_counts: dict[
        tuple[str, date],
        int,
    ] = {}

    for input_path in input_paths:
        records = iter_jsonl_records(
            input_path
        )

        # 레코드 흐름을 끊지 않고 검수 표본을 수집한 뒤
        # 같은 레코드를 일별 집계기로 전달한다.
        records_with_samples = (
            _iter_records_with_token_samples(
                records=records,
                token_sample_rows=token_sample_rows,
                sample_counts=sample_counts,
                sample_size=token_sample_size,
            )
        )

        daily_documents = iter_daily_documents(
            records_with_samples
        )

        yield from daily_documents


def run_daily_tfidf_review(
    input_paths: tuple[Path, ...],
) -> None:
    """
    전체 종목의 일별 TF-IDF 결과를 검수용 CSV로 저장한다.
    """
    # 입력 JSONL 경로 목록이 비어 있는지 확인한다
    if not input_paths:
        raise FileNotFoundError(
            "입력 JSONL 파일을 찾을 수 없습니다: "
            f"{INPUT_DIR / INPUT_PATTERN}"
        )

    # 종목·날짜별 원문과 토큰화 결과 표본을 적재할 목록을 만든다.
    token_sample_rows: list[dict] = []

    # 입력 경로를 순회하며 토큰화 표본과 일별 집계 문서를
    # 요청 시 하나씩 만들 generator 객체를 생성한다.
    all_daily_documents = (
        _iter_daily_documents_from_paths(
            input_paths=input_paths,
            token_sample_rows=token_sample_rows,
            token_sample_size=TOKEN_SAMPLE_PER_DAY,
        )
    )

    # TF-IDF 행렬의 각 행과 같은 순서로 메타데이터를 적재할 목록을 만든다.
    metadata_rows: list[dict] = []

    # 일별 문서를 순회하면서 메타데이터를 같은 순서로 저장하고
    # TF-IDF 입력 문자열만 하나씩 반환한다.
    def iter_tfidf_texts() -> Iterator[str]:
        for document in all_daily_documents:
            tfidf_text = document["tfidf_text"]

            # TF-IDF 입력은 토큰 사이를 공백 하나로 연결하므로
            # 큰 임시 목록을 만들지 않고 공백 수로 토큰 개수를 계산한다.
            token_count = (
                tfidf_text.count(" ") + 1
                if tfidf_text
                else 0
            )

            metadata_rows.append(
                {
                    "stock_code": document["stock_code"],
                    "model_date": document["model_date"],
                    "comment_count": document["comment_count"],
                    "token_count": token_count,
                }
            )

            yield tfidf_text

    # 일별 문서에서 TF-IDF 입력 문자열만 반환할 generator를 생성한다
    tfidf_texts = iter_tfidf_texts()

    # 검수 실행기가 선택한 설정으로 TF-IDF 벡터라이저를 생성한다.
    vectorizer = create_tfidf_vectorizer(
        lowercase=LOWERCASE,
        ngram_range=NGRAM_RANGE,
        min_df=MIN_DF,
        max_df=MAX_DF,
        max_features=MAX_FEATURES,
        sublinear_tf=SUBLINEAR_TF,
    )

    # generator를 소비하며 vocabulary와 IDF를 학습하고
    # 일별 문서를 TF-IDF 희소행렬로 변환한다
    tfidf_matrix = vectorizer.fit_transform(
        tfidf_texts
    )
    # 학습된 행렬의 열 번호와 대응하는 feature 이름을 가져온다
    feature_names = vectorizer.get_feature_names_out()

    # 일별 문서 메타데이터를 정해진 컬럼 순서의 DataFrame으로 변환한다.
    metadata_df = pd.DataFrame(
        metadata_rows,
        columns=[
            "stock_code",
            "model_date",
            "comment_count",
            "token_count",
        ],
    )

    # 각 일별 문서에서 TF-IDF 점수가 0이 아닌 feature 수를 기록한다.
    metadata_df["nonzero_feature_count"] = (
        tfidf_matrix.getnnz(axis=1)
    )

    # 원문과 토큰화 결과의 제한된 표본을 검수용 DataFrame으로 변환한다.
    token_sample_df = pd.DataFrame(
        token_sample_rows,
        columns=[
            "stock_code",
            "model_date",
            "comment_id",
            "created_at",
            "text",
            "kiwi_tokens",
            "tfidf_text",
        ],
    )

    # 전체 feature와 IDF를 저장하기 위한 DataFrame으로 변환한다.
    feature_review_df = _create_feature_review_dataframe(
        vectorizer
    )

    # 일별 문서마다 점수가 높은 feature를 저장할 DataFrame으로 변환한다.
    tfidf_score_review_df = (
        _create_tfidf_score_review_dataframe(
            metadata_df=metadata_df,
            tfidf_matrix=tfidf_matrix,
            feature_names=feature_names,
            top_n=TOP_N,
        )
    )

    _save_csv(
        metadata_df,
        DAILY_METADATA_REVIEW_PATH,
    )

    _save_csv(
        token_sample_df,
        DAILY_TOKEN_SAMPLE_REVIEW_PATH,
    )

    _save_csv(
        feature_review_df,
        DAILY_FEATURE_REVIEW_PATH,
    )

    _save_csv(
        tfidf_score_review_df,
        DAILY_TFIDF_SCORE_REVIEW_PATH,
    )


if __name__ == "__main__":
    run_daily_tfidf_review(
        INPUT_PATHS
    )
