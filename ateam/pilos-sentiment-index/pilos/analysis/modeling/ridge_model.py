from sklearn.linear_model import Ridge


def create_ridge_model(
    *,
    alpha: float = 1.0,
    fit_intercept: bool = True,
    solver: str = "lsqr",
    tol: float = 1e-4,
    max_iter: int | None = None,
    positive: bool = False,
) -> Ridge:
    """지정한 하이퍼파라미터로 Ridge 회귀 모델을 생성한다."""
    return Ridge(
        alpha=alpha,
        fit_intercept=fit_intercept,
        solver=solver,
        tol=tol,
        max_iter=max_iter,
        positive=positive,
    )
