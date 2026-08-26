"""학원 BGE-Reranker 서버에서 재정렬용 벡터를 가져온다."""

import math
import os
import time

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from dotenv import load_dotenv


class RerankerClientError(RuntimeError):
    """학원 Reranker 호출 형식을 제거한 공통 오류다."""


class RerankerTransportError(RerankerClientError):
    """재시도 후에도 완료되지 않은 연결 또는 HTTP 오류다."""


class RerankerResponseError(RerankerClientError):
    """Reranker 서버의 벡터 응답 형식이 잘못된 오류다."""


@dataclass(frozen=True, slots=True)
class RerankerClientSettings:
    """학원 Reranker 서버의 연결 설정이다."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "RerankerClientSettings":
        """환경변수를 읽고 Reranker 연결 설정을 검증한다."""
        load_dotenv()

        base_url = os.getenv(
            "RERANK_BASE_URL",
            "",
        ).strip().rstrip("/")
        api_key = os.getenv(
            "RERANK_API_KEY",
            "EMPTY",
        ).strip() or "EMPTY"
        model = os.getenv(
            "RERANK_MODEL",
            "",
        ).strip()

        missing = [
            name
            for name, value in {
                "RERANK_BASE_URL": base_url,
                "RERANK_MODEL": model,
            }.items()
            if not value
        ]

        if missing:
            raise ValueError(
                "Reranker 필수 환경변수가 비어 있습니다: "
                f"{missing}"
            )

        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                "RERANK_BASE_URL은 http:// 또는 https://로 "
                "시작해야 합니다."
            )

        timeout_text = os.getenv(
            "RERANK_TIMEOUT_SECONDS",
            "120",
        ).strip() or "120"

        try:
            timeout_seconds = float(timeout_text)
        except ValueError as error:
            raise ValueError(
                "RERANK_TIMEOUT_SECONDS는 숫자여야 합니다."
            ) from error

        if timeout_seconds <= 0:
            raise ValueError(
                "RERANK_TIMEOUT_SECONDS는 0보다 커야 합니다."
            )

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )


class AcademyRerankerClient:
    """학원 8091 서버의 /v1/embeddings 규격을 호출한다."""

    def __init__(
        self,
        *,
        settings: RerankerClientSettings,
        post: Callable[..., httpx.Response] = httpx.post,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._post = post
        self._sleep = sleep

    def encode_query(self, query: str) -> list[float]:
        """질문 한 건을 리랭킹 서버의 벡터로 변환한다."""
        cleaned_query = _normalize_text(query, field_name="query")
        return self._request_embeddings(cleaned_query)[0]

    def encode_documents(
        self,
        documents: Sequence[str],
    ) -> list[list[float]]:
        """후보 문서 목록을 리랭킹 서버의 벡터로 변환한다."""
        normalized_documents = _normalize_texts(documents)
        return self._request_embeddings(normalized_documents)

    def _request_embeddings(
        self,
        input_value: str | list[str],
    ) -> list[list[float]]:
        expected_count = (
            1
            if isinstance(input_value, str)
            else len(input_value)
        )
        headers = {
            "Connection": "close",
        }

        if self._settings.api_key != "EMPTY":
            headers["Authorization"] = (
                f"Bearer {self._settings.api_key}"
            )

        delays = (1.0, 2.0)

        for attempt in range(3):
            try:
                response = self._post(
                    f"{self._settings.base_url}/embeddings",
                    # 전용 포트가 모델을 고정하므로 강의 예제처럼
                    # payload에는 model이 아니라 input만 보낸다.
                    json={"input": input_value},
                    headers=headers,
                    timeout=self._settings.timeout_seconds,
                )
                response.raise_for_status()
                return _normalize_response(
                    response.json(),
                    expected_count=expected_count,
                )
            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.PoolTimeout,
            ) as error:
                if attempt == 2:
                    raise RerankerTransportError(
                        "Reranker 연결 요청이 3회 실패했습니다: "
                        f"{type(error).__name__}"
                    ) from None
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code

                if not _is_retryable_status(status_code):
                    raise RerankerTransportError(
                        "재시도하지 않는 Reranker HTTP 오류입니다: "
                        f"status_code={status_code}"
                    ) from None

                if attempt == 2:
                    raise RerankerTransportError(
                        "Reranker HTTP 요청이 3회 실패했습니다: "
                        f"status_code={status_code}"
                    ) from None
            except (ValueError, TypeError) as error:
                raise RerankerResponseError(
                    "Reranker 응답 JSON을 해석할 수 없습니다: "
                    f"{type(error).__name__}"
                ) from None
            except RerankerClientError:
                raise
            except Exception as error:
                raise RerankerClientError(
                    "Reranker 호출 중 예상하지 못한 오류가 발생했습니다: "
                    f"{type(error).__name__}"
                ) from None

            self._sleep(delays[attempt])

        raise AssertionError(
            "Reranker 재시도 루프가 결과 없이 종료됐습니다."
        )


def _normalize_text(
    text: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(text, str):
        raise TypeError(
            f"{field_name}는 문자열이어야 합니다."
        )

    cleaned = text.strip()

    if not cleaned:
        raise ValueError(
            f"{field_name}는 비어 있을 수 없습니다."
        )

    return cleaned


def _normalize_texts(texts: Sequence[str]) -> list[str]:
    if isinstance(texts, (str, bytes)):
        raise TypeError(
            "documents는 문자열 하나가 아니라 목록이어야 합니다."
        )

    normalized = [
        _normalize_text(text, field_name="document")
        for text in texts
    ]

    if not normalized:
        raise ValueError(
            "Rerank할 문서가 한 개 이상 필요합니다."
        )

    return normalized


def _normalize_response(
    payload: Any,
    *,
    expected_count: int,
) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise RerankerResponseError(
            "Reranker 응답은 JSON object여야 합니다."
        )

    data = payload.get("data")

    if not isinstance(data, list) or len(data) != expected_count:
        raise RerankerResponseError(
            "Reranker 입력 개수와 응답 개수가 다릅니다."
        )

    ordered_items = sorted(
        data,
        key=lambda item: (
            item.get("index", -1)
            if isinstance(item, dict)
            else -1
        ),
    )
    vectors: list[list[float]] = []
    vector_dimension: int | None = None

    for expected_index, item in enumerate(ordered_items):
        if (
            not isinstance(item, dict)
            or item.get("index") != expected_index
        ):
            raise RerankerResponseError(
                "Reranker 응답 index가 입력 순서와 다릅니다."
            )

        embedding = _get_vector(
            item.get("embedding")
        )

        if not isinstance(embedding, list) or not embedding:
            raise RerankerResponseError(
                "Reranker 응답 벡터가 비어 있습니다."
            )

        try:
            vector = [float(value) for value in embedding]
        except (TypeError, ValueError):
            raise RerankerResponseError(
                "Reranker 벡터에 숫자가 아닌 값이 있습니다."
            ) from None

        if not all(math.isfinite(value) for value in vector):
            raise RerankerResponseError(
                "Reranker 벡터에 유한하지 않은 값이 있습니다."
            )

        if vector_dimension is None:
            vector_dimension = len(vector)
        elif len(vector) != vector_dimension:
            raise RerankerResponseError(
                "Reranker 응답 벡터 차원이 서로 다릅니다."
            )

        vectors.append(vector)

    return vectors


def _get_vector(value: Any) -> Any:
    """강의 서버의 토큰별 중첩 응답에서 첫 벡터를 꺼낸다."""
    if (
        isinstance(value, list)
        and value
        and isinstance(value[0], list)
    ):
        return value[0]

    return value


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 429} or status_code >= 500
