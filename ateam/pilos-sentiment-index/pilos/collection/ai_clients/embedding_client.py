"""OpenAI 호환 학원 서버에서 BGE-M3 Embedding을 가져온다."""

import math
import os
import time

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
)


EMBEDDING_DIMENSION = 1024


class EmbeddingClientError(RuntimeError):
    """공급자 SDK 형식을 제거한 공통 Embedding 오류다."""


class EmbeddingTransportError(EmbeddingClientError):
    """재시도 후에도 완료되지 않은 연결 또는 HTTP 오류다."""


class EmbeddingResponseError(EmbeddingClientError):
    """서버 응답의 개수·순서·벡터 형식이 잘못된 오류다."""


@dataclass(frozen=True, slots=True)
class EmbeddingClientSettings:
    """학원 Embedding 서버의 연결 설정이다."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "EmbeddingClientSettings":
        """환경변수를 읽고 Embedding 연결 설정을 검증한다."""
        load_dotenv()

        base_url = os.getenv(
            "EMBEDDING_BASE_URL",
            "",
        ).strip().rstrip("/")
        api_key = os.getenv(
            "EMBEDDING_API_KEY",
            "EMPTY",
        ).strip() or "EMPTY"
        model = os.getenv(
            "EMBEDDING_MODEL",
            "",
        ).strip()

        missing = [
            name
            for name, value in {
                "EMBEDDING_BASE_URL": base_url,
                "EMBEDDING_MODEL": model,
            }.items()
            if not value
        ]

        if missing:
            raise ValueError(
                "Embedding 필수 환경변수가 비어 있습니다: "
                f"{missing}"
            )

        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                "EMBEDDING_BASE_URL은 http:// 또는 https://로 "
                "시작해야 합니다."
            )

        timeout_text = os.getenv(
            "EMBEDDING_TIMEOUT_SECONDS",
            "120",
        ).strip() or "120"

        try:
            timeout_seconds = float(timeout_text)
        except ValueError as error:
            raise ValueError(
                "EMBEDDING_TIMEOUT_SECONDS는 숫자여야 합니다."
            ) from error

        if timeout_seconds <= 0:
            raise ValueError(
                "EMBEDDING_TIMEOUT_SECONDS는 0보다 커야 합니다."
            )

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )


def create_openai_compatible_embedding_client(
    settings: EmbeddingClientSettings,
) -> OpenAI:
    """SDK 자동 재시도 없이 OpenAI 호환 클라이언트를 만든다."""
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        max_retries=0,
    )


class OpenAICompatibleEmbeddingClient:
    """학원 BGE-M3 서버를 호출하고 1024차원 벡터를 반환한다."""

    def __init__(
        self,
        *,
        settings: EmbeddingClientSettings,
        sdk_client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._sdk_client = (
            sdk_client
            or create_openai_compatible_embedding_client(settings)
        )

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """문서 여러 개를 한 번의 batch 요청으로 변환한다."""
        normalized_texts = _normalize_texts(texts)
        response = self._create_embeddings(normalized_texts)
        return _normalize_response(
            response,
            expected_count=len(normalized_texts),
        )

    def embed_query(self, query: str) -> list[float]:
        """사용자 질문 하나를 검색용 벡터로 변환한다."""
        return self.embed_documents([query])[0]

    def _create_embeddings(self, texts: list[str]) -> Any:
        delays = (1.0, 2.0)

        for attempt in range(3):
            try:
                return self._sdk_client.embeddings.create(
                    model=self._settings.model,
                    input=texts,
                )
            except (APIConnectionError, APITimeoutError) as error:
                if attempt == 2:
                    raise EmbeddingTransportError(
                        "Embedding 연결 요청이 3회 실패했습니다: "
                        f"{type(error).__name__}"
                    ) from None
            except APIStatusError as error:
                if not _is_retryable_status(error.status_code):
                    raise EmbeddingTransportError(
                        "재시도하지 않는 Embedding HTTP 오류입니다: "
                        f"status_code={error.status_code}"
                    ) from None

                if attempt == 2:
                    raise EmbeddingTransportError(
                        "Embedding HTTP 요청이 3회 실패했습니다: "
                        f"status_code={error.status_code}"
                    ) from None
            except Exception as error:
                raise EmbeddingClientError(
                    "Embedding SDK에서 예상하지 못한 오류가 발생했습니다: "
                    f"{type(error).__name__}"
                ) from None

            self._sleep(delays[attempt])

        raise AssertionError(
            "Embedding 재시도 루프가 결과 없이 종료됐습니다."
        )


def _normalize_texts(texts: Sequence[str]) -> list[str]:
    if isinstance(texts, (str, bytes)):
        raise TypeError(
            "texts는 문자열 하나가 아니라 문자열 목록이어야 합니다."
        )

    normalized: list[str] = []

    for text in texts:
        if not isinstance(text, str):
            raise TypeError(
                "Embedding 입력은 모두 문자열이어야 합니다."
            )

        cleaned = text.strip()

        if not cleaned:
            raise ValueError(
                "빈 문자열은 Embedding할 수 없습니다."
            )

        normalized.append(cleaned)

    if not normalized:
        raise ValueError(
            "Embedding할 문장이 한 개 이상 필요합니다."
        )

    return normalized


def _normalize_response(
    response: Any,
    *,
    expected_count: int,
) -> list[list[float]]:
    data = getattr(response, "data", None)

    if not isinstance(data, list) or len(data) != expected_count:
        raise EmbeddingResponseError(
            "Embedding 입력 개수와 응답 개수가 다릅니다."
        )

    ordered_items = sorted(
        data,
        key=lambda item: getattr(item, "index", -1),
    )
    expected_indexes = list(range(expected_count))
    actual_indexes = [
        getattr(item, "index", None)
        for item in ordered_items
    ]

    if actual_indexes != expected_indexes:
        raise EmbeddingResponseError(
            "Embedding 응답 index가 입력 순서와 일치하지 않습니다."
        )

    vectors: list[list[float]] = []

    for item in ordered_items:
        embedding = getattr(item, "embedding", None)

        if (
            not isinstance(embedding, list)
            or len(embedding) != EMBEDDING_DIMENSION
        ):
            raise EmbeddingResponseError(
                "Embedding 벡터는 1024차원이어야 합니다."
            )

        try:
            vector = [float(value) for value in embedding]
        except (TypeError, ValueError):
            raise EmbeddingResponseError(
                "Embedding 벡터에 숫자가 아닌 값이 있습니다."
            ) from None

        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingResponseError(
                "Embedding 벡터에 유한하지 않은 값이 있습니다."
            )

        vectors.append(vector)

    return vectors


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 429} or status_code >= 500
