import numpy as np
import pandas as pd
from scipy.sparse import (
    csr_matrix,
    hstack,
    spmatrix,
)
from sklearn.preprocessing import StandardScaler


def create_log_comment_count_feature(
    dataset: pd.DataFrame,
) -> np.ndarray:
    """
    Dataset의 댓글 수를 검증하고 log1p 변환한
    2차원 실수형 특성 배열을 생성한다.
    """
    # 댓글 수 특성을 만들기 위한 원본 컬럼이 존재하는지 확인한다
    if "comment_count" not in dataset.columns:
        raise ValueError(
            "Dataset에 comment_count 컬럼이 없습니다."
        )

    comment_count_series = dataset[
        "comment_count"
    ]

    # 결측 댓글 수는 실제 댓글 활동량을 나타낼 수 없다
    if comment_count_series.isna().any():
        raise ValueError(
            "comment_count에 결측값이 있습니다."
        )

    # 숫자로 변환할 수 없는 댓글 수가 있으면
    # 원인을 알 수 있는 오류로 변환한다
    try:
        comment_counts = pd.to_numeric(
            comment_count_series,
            errors="raise",
        ).to_numpy(
            dtype=float,
            copy=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "comment_count를 실수형 특성값으로 "
            "변환할 수 없습니다."
        ) from error

    # 빈 특성 배열은 스케일러와 모델의 입력으로 사용할 수 없다
    if comment_counts.size == 0:
        raise ValueError(
            "comment_count가 비어 있습니다."
        )

    # 무한대는 결측값은 아니지만 모델 입력으로 사용할 수 없다
    if not np.isfinite(comment_counts).all():
        raise ValueError(
            "comment_count에 유한하지 않은 값이 있습니다."
        )

    # 댓글 수는 개수를 의미하므로 음수나 소수일 수 없다
    if (
        (comment_counts < 0).any()
        or (comment_counts % 1 != 0).any()
    ):
        raise ValueError(
            "comment_count는 0 이상의 정수여야 합니다."
        )

    # 종목·날짜별 댓글 수의 큰 편차를 줄이고
    # 0개인 경우도 유지하기 위해 log가 아닌 log1p를 적용한다
    log_comment_counts = np.log1p(
        comment_counts
    )

    # StandardScaler와 희소행렬 열 결합에 사용할 수 있도록
    # (문서 수, 1) 형태의 2차원 배열로 변환한다
    return log_comment_counts.reshape(-1, 1)


def fit_transform_comment_count_feature(
    dataset: pd.DataFrame,
) -> tuple[np.ndarray, StandardScaler]:
    """
    훈련 Dataset의 로그 댓글 수로 스케일러를 학습하고
    표준화된 댓글 수 특성과 스케일러를 반환한다.
    """
    log_comment_counts = (
        create_log_comment_count_feature(
            dataset
        )
    )

    comment_count_scaler = StandardScaler()

    # 검증·추론 데이터의 정보가 학습에 유입되지 않도록
    # 훈련 데이터에서만 평균과 표준편차를 학습한다
    scaled_comment_counts = (
        comment_count_scaler.fit_transform(
            log_comment_counts
        )
    )

    return (
        scaled_comment_counts,
        comment_count_scaler,
    )


def transform_comment_count_feature(
    dataset: pd.DataFrame,
    scaler: StandardScaler,
) -> np.ndarray:
    """
    학습된 스케일러로 Dataset의 로그 댓글 수를
    표준화된 댓글 수 특성으로 변환한다.
    """
    log_comment_counts = (
        create_log_comment_count_feature(
            dataset
        )
    )

    # 검증과 추론에서도 훈련 데이터의 기준을 유지하도록
    # 전달받은 스케일러를 다시 학습하지 않고 변환만 수행한다
    return scaler.transform(
        log_comment_counts
    )


def combine_model_features(
    tfidf_features: spmatrix,
    comment_count_feature: np.ndarray,
) -> csr_matrix:
    """
    TF-IDF 특성과 표준화된 로그 댓글 수 특성을
    Ridge 입력용 CSR 희소행렬로 결합한다.
    """
    if (
        comment_count_feature.ndim != 2
        or comment_count_feature.shape[1] != 1
    ):
        raise ValueError(
            "댓글 수 특성은 (문서 수, 1) 형태여야 합니다."
        )

    # 같은 문서 순서로 생성된 두 특성의 행 수가 일치해야
    # 각 TF-IDF 행에 올바른 댓글 수를 연결할 수 있다
    if (
        tfidf_features.shape[0]
        != comment_count_feature.shape[0]
    ):
        raise ValueError(
            "TF-IDF 특성과 댓글 수 특성의 행 수가 다릅니다."
        )

    if not np.isfinite(
        comment_count_feature
    ).all():
        raise ValueError(
            "댓글 수 특성에 유한하지 않은 값이 있습니다."
        )

    # 밀집 배열인 댓글 수 특성을 희소행렬로 바꾼 뒤
    # TF-IDF의 마지막 열에 연결하여 메모리 효율을 유지한다
    return hstack(
        [
            tfidf_features,
            csr_matrix(comment_count_feature),
        ],
        format="csr",
    )
