import numpy as np
from scipy.sparse import spmatrix
from sklearn.linear_model import Ridge


def split_text_only_ridge_coefficients(
    model: Ridge,
    text_feature_count: int,
) -> tuple[np.ndarray, float]:
    """
    text-only Ridge의 텍스트 계수와 절편을 검증하여 반환한다.

    입력:
    - model: TF-IDF 특성만으로 fit한 단일 출력 Ridge 모델이다.
    - text_feature_count: 모델과 함께 저장된 Vectorizer의 전체 특성
      개수다. Ridge 입력 열 수와 정확히 같아야 한다.

    출력:
    - 첫 번째 값은 TF-IDF 열 순서와 같은 텍스트 계수 배열이다.
    - 두 번째 값은 목표 수급지수 평균 수준을 표현하는 절편이다.

    선정 모델은 댓글 수 특성을 사용하지 않는다. 따라서 Ridge 계수에
    TF-IDF 특성 수보다 한 개 많은 열이 있으면 구형 bundle 또는 잘못된
    모델 입력으로 판단하여 오류를 발생시킨다.
    """
    if (
        not isinstance(text_feature_count, int)
        or isinstance(text_feature_count, bool)
        or text_feature_count <= 0
    ):
        raise ValueError(
            "텍스트 특성 수는 1 이상이어야 합니다."
        )

    # 학습되지 않은 Ridge 모델에는
    # 특성별 계수와 절편이 존재하지 않는다
    if (
        not hasattr(model, "coef_")
        or not hasattr(model, "intercept_")
    ):
        raise ValueError(
            "학습되지 않은 Ridge 모델입니다."
        )

    coefficients = np.asarray(
        model.coef_,
        dtype=float,
    )

    # 현재 모델은 하나의 수급지수만 예측하므로
    # 계수는 특성 수와 같은 길이의 1차원 배열이어야 한다
    if coefficients.ndim != 1:
        raise ValueError(
            "Ridge 계수는 1차원 배열이어야 합니다."
        )

    if coefficients.size != text_feature_count:
        raise ValueError(
            "text-only Ridge 계수 수와 TF-IDF 특성 수가 다릅니다."
        )

    if not np.isfinite(coefficients).all():
        raise ValueError(
            "Ridge 계수에 유한하지 않은 값이 있습니다."
        )

    intercept_values = np.asarray(
        model.intercept_,
        dtype=float,
    ).reshape(-1)

    # 하나의 수급지수를 예측하는 모델이므로
    # 절편도 하나만 존재해야 한다
    if intercept_values.size != 1:
        raise ValueError(
            "Ridge 절편은 하나여야 합니다."
        )

    intercept = float(
        intercept_values[0]
    )

    if not np.isfinite(intercept):
        raise ValueError(
            "Ridge 절편이 유한하지 않습니다."
        )

    return (
        coefficients.copy(),
        intercept,
    )


def analyze_text_contributions(
    tfidf_row: spmatrix,
    feature_names: np.ndarray,
    text_coefficients: np.ndarray,
    top_n: int = 10,
) -> dict:
    """
    한 문서의 TF-IDF 값과 Ridge 계수를 결합하여
    텍스트 연관 점수와 주요 단어별 기여도를 계산한다.
    """
    if top_n <= 0:
        raise ValueError(
            "top_n은 1 이상이어야 합니다."
        )

    if tfidf_row.shape[0] != 1:
        raise ValueError(
            "TF-IDF 입력은 문서 한 행이어야 합니다."
        )

    feature_names = np.asarray(
        feature_names
    )

    if feature_names.ndim != 1:
        raise ValueError(
            "TF-IDF 특성 이름은 1차원 배열이어야 합니다."
        )

    text_coefficients = np.asarray(
        text_coefficients,
        dtype=float,
    )

    if text_coefficients.ndim != 1:
        raise ValueError(
            "텍스트 특성 계수는 1차원 배열이어야 합니다."
        )

    # TF-IDF 행렬의 열 번호, 특성 이름,
    # Ridge 텍스트 계수가 모두 같은 단어를 가리켜야 한다
    text_feature_count = tfidf_row.shape[1]

    if (
        feature_names.size != text_feature_count
        or text_coefficients.size != text_feature_count
    ):
        raise ValueError(
            "TF-IDF 열 수, 특성 이름 수, "
            "텍스트 계수 수가 다릅니다."
        )

    if not np.isfinite(
        text_coefficients
    ).all():
        raise ValueError(
            "텍스트 특성 계수에 유한하지 않은 값이 있습니다."
        )

    # 희소행렬의 0이 아닌 값과 열 번호에
    # 효율적으로 접근할 수 있도록 CSR 형식으로 변환한다
    row = tfidf_row.tocsr()

    feature_indices = row.indices
    tfidf_values = row.data

    if not np.isfinite(tfidf_values).all():
        raise ValueError(
            "TF-IDF 값에 유한하지 않은 값이 있습니다."
        )

    # 현재 문서에 실제로 등장한 단어마다
    # TF-IDF 값과 학습된 단어 계수를 곱하여 기여도를 계산한다
    contributions = (
        tfidf_values
        * text_coefficients[feature_indices]
    )

    # 모든 단어 기여도의 합은 댓글 수와 절편을 제외한
    # 현재 문서의 텍스트 연관 점수다
    text_score = float(
        contributions.sum()
    )

    # 양수 기여도는 큰 값부터 정렬하여
    # 개인투자자 거래우위의 양수 방향 주요 단어를 선택한다
    positive_positions = np.flatnonzero(
        contributions > 0
    )
    positive_positions = positive_positions[
        np.argsort(
            -contributions[positive_positions]
        )
    ][:top_n]

    # 음수 기여도는 작은 값부터 정렬하여
    # 개인투자자 거래우위의 음수 방향 주요 단어를 선택한다
    negative_positions = np.flatnonzero(
        contributions < 0
    )
    negative_positions = negative_positions[
        np.argsort(
            contributions[negative_positions]
        )
    ][:top_n]

    positive_keywords = []

    for rank, position in enumerate(
        positive_positions,
        start=1,
    ):
        feature_index = feature_indices[
            position
        ]

        positive_keywords.append(
            {
                "rank": rank,
                "word": str(
                    feature_names[feature_index]
                ),
                "tfidf": float(
                    tfidf_values[position]
                ),
                "coefficient": float(
                    text_coefficients[
                        feature_index
                    ]
                ),
                "contribution": float(
                    contributions[position]
                ),
            }
        )

    negative_keywords = []

    for rank, position in enumerate(
        negative_positions,
        start=1,
    ):
        feature_index = feature_indices[
            position
        ]

        negative_keywords.append(
            {
                "rank": rank,
                "word": str(
                    feature_names[feature_index]
                ),
                "tfidf": float(
                    tfidf_values[position]
                ),
                "coefficient": float(
                    text_coefficients[
                        feature_index
                    ]
                ),
                "contribution": float(
                    contributions[position]
                ),
            }
        )

    return {
        "text_score": text_score,
        "recognized_feature_count": int(
            feature_indices.size
        ),
        "positive_keywords": positive_keywords,
        "negative_keywords": negative_keywords,
    }
