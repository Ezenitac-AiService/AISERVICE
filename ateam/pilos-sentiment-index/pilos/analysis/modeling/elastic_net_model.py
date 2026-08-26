from typing import Literal

from sklearn.linear_model import ElasticNet


ElasticNetSelection = Literal[
    "cyclic",
    "random",
]


def create_elastic_net_model(
    *,
    alpha: float,
    l1_ratio: float,
    fit_intercept: bool = True,
    max_iter: int = 10_000,
    tol: float = 1e-4,
    selection: ElasticNetSelection = "cyclic",
) -> ElasticNet:
    """
    전달받은 규제 설정으로 ElasticNet 회귀 모델을 생성한다.

    입력:
    - alpha: 전체 규제 강도다. 값이 클수록 모든 회귀계수를 더 강하게
      축소한다. Ridge의 alpha와 목적함수 스케일이 달라 같은 숫자를
      동일한 규제 강도로 해석하지 않는다.
    - l1_ratio: 전체 규제에서 L1 규제가 차지하는 비율이다. 1에
      가까울수록 불필요한 특성 계수를 정확히 0으로 만드는 성질이
      강해진다.
    - fit_intercept: 목표값의 평균 수준을 표현할 절편 학습 여부다.
    - max_iter: 좌표 하강 최적화가 수행할 최대 반복 횟수다.
    - tol: 최적화 수렴을 판단하는 허용 오차다.
    - selection: 계수를 갱신할 순서다. cyclic은 정해진 순서를
      반복하고 random은 매 반복에서 무작위 순서를 사용한다.

    출력:
    - 아직 학습되지 않은 sklearn ElasticNet 모델을 반환한다.
      호출자는 훈련 특성과 목표값을 전달하여 fit을 수행해야 한다.
    """
    if alpha <= 0:
        raise ValueError(
            "ElasticNet alpha는 0보다 커야 합니다."
        )

    if not 0 < l1_ratio <= 1:
        raise ValueError(
            "ElasticNet l1_ratio는 0보다 크고 1 이하여야 합니다."
        )

    if max_iter <= 0:
        raise ValueError(
            "ElasticNet max_iter는 1 이상이어야 합니다."
        )

    if tol <= 0:
        raise ValueError(
            "ElasticNet tol은 0보다 커야 합니다."
        )

    if selection not in {
        "cyclic",
        "random",
    }:
        raise ValueError(
            "ElasticNet selection은 cyclic 또는 random이어야 합니다."
        )

    return ElasticNet(
        alpha=alpha,
        l1_ratio=l1_ratio,
        fit_intercept=fit_intercept,
        max_iter=max_iter,
        tol=tol,
        selection=selection,
    )
