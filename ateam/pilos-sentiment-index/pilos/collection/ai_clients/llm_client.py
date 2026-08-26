import os
import time

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
)


THINKING_COMPLETED_PREFILL = "<think>\n\n</think>\n\n"


class LlmClientError(RuntimeError):
    """공급자 SDK 예외를 제거한 공통 LLM 클라이언트 오류다."""


class LlmTransportError(LlmClientError):
    """재시도 후에도 완료되지 않은 연결 또는 HTTP 오류다."""


class LlmResponseError(LlmClientError):
    """LLM 응답이 공통 Chat Completions 계약을 지키지 않은 오류다."""


@dataclass(frozen=True, slots=True)
class LlmClientSettings:
    """OpenAI 호환 LLM 서버의 공통 연결 설정이다."""

    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "LlmClientSettings":
        """챗봇 환경변수를 읽고 필수 연결 설정을 검증한다."""
        load_dotenv()

        provider = os.getenv("LLM_PROVIDER", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
        api_key = os.getenv("LLM_API_KEY", "").strip()
        model = _first_env_value(
            "CHAT_LLM_MODEL",
            "LLM_MODEL",
            "REPORT_LLM_MODEL",
        )
        values = {
            "LLM_PROVIDER": provider,
            "LLM_BASE_URL": base_url,
            "LLM_API_KEY": api_key,
            "CHAT_LLM_MODEL": model,
        }
        missing = [name for name, value in values.items() if not value]

        if missing:
            raise ValueError(
                "LLM 필수 환경변수가 비어 있습니다: "
                f"{missing}"
            )

        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                "LLM_BASE_URL은 http:// 또는 https://로 시작해야 합니다."
            )

        timeout_text = _first_env_value(
            "CHAT_LLM_TIMEOUT_SECONDS",
            "LLM_TIMEOUT_SECONDS",
            "REPORT_LLM_TIMEOUT_SECONDS",
        ) or "120"

        try:
            timeout_seconds = float(timeout_text)
        except ValueError as error:
            raise ValueError(
                "LLM timeout 환경변수는 숫자여야 합니다."
            ) from error

        if timeout_seconds <= 0:
            raise ValueError("LLM timeout은 0보다 커야 합니다.")

        return cls(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True, slots=True)
class ChatCompletionResult:
    """공급자 SDK 형식을 제거한 텍스트 채팅 응답이다."""

    content: str
    provider_response_id: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str | None


def _first_env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()

        if value:
            return value

    return ""


def create_openai_compatible_client(
    settings: LlmClientSettings,
) -> OpenAI:
    """SDK 자동 재시도 없이 OpenAI 호환 클라이언트를 만든다."""
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        max_retries=0,
    )


def _extract_usage(completion: Any) -> tuple[int | None, int | None]:
    usage = getattr(completion, "usage", None)

    if usage is None:
        return None, None

    input_tokens = getattr(usage, "prompt_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    return (
        None if input_tokens is None else int(input_tokens),
        None if output_tokens is None else int(output_tokens),
    )


def _normalize_messages(
    messages: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    if not messages:
        raise ValueError("LLM messages는 한 건 이상이어야 합니다.")

    normalized: list[dict[str, str]] = []

    for index, message in enumerate(messages):
        role = message.get("role")
        content = message.get("content")

        if not isinstance(role, str) or not role.strip():
            raise ValueError(
                f"LLM messages[{index}].role이 비어 있습니다."
            )

        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                f"LLM messages[{index}].content가 비어 있습니다."
            )

        normalized.append(
            {
                "role": role.strip(),
                "content": content,
            }
        )

    return normalized


class OpenAICompatibleLlmClient:
    """OpenAI 호환 Chat Completions를 호출하는 공통 구현체다."""

    def __init__(
        self,
        *,
        settings: LlmClientSettings,
        sdk_client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._sdk_client = sdk_client or create_openai_compatible_client(
            settings
        )

    def create_chat_completion(
        self,
        *,
        messages: Sequence[Mapping[str, str]],
        temperature: float = 0.3,
        top_p: float = 0.85,
        max_tokens: int = 1024,
        skip_thinking: bool = False,
    ) -> ChatCompletionResult:
        """텍스트 채팅을 호출하고 공급자 중립 결과를 반환한다 (Spec 037 Top-P 0.85 적용)."""
        if not 0 <= temperature <= 2:
            raise ValueError("temperature는 0 이상 2 이하여야 합니다.")

        if not 0 <= top_p <= 1:
            raise ValueError("top_p는 0 이상 1 이하여야 합니다.")

        if max_tokens <= 0:
            raise ValueError("max_tokens는 0보다 커야 합니다.")

        normalized_messages = _normalize_messages(messages)

        if skip_thinking:
            normalized_messages.append(
                {
                    "role": "assistant",
                    "content": THINKING_COMPLETED_PREFILL,
                }
            )

        arguments: dict[str, Any] = {
            "model": self._settings.model,
            "messages": normalized_messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "extra_body": {"priority": "high", "repetition_penalty": 1.05},
        }
        completion = self._create_completion(arguments)

        try:
            choices = getattr(completion, "choices", None)

            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError(
                    "LLM 응답 choices는 정확히 한 건이어야 합니다."
                )

            choice = choices[0]
            message = getattr(choice, "message", None)

            if getattr(message, "refusal", None):
                raise ValueError("LLM이 채팅 응답을 거절했습니다.")

            content = getattr(message, "content", None)

            if not isinstance(content, str) or not content.strip():
                raise ValueError("LLM 채팅 응답 본문이 비어 있습니다.")

            finish_reason = getattr(choice, "finish_reason", None)

            if skip_thinking and finish_reason == "length":
                raise ValueError(
                    "LLM이 최종 답변을 완료하기 전에 토큰 한도에 도달했습니다."
                )

            content = _extract_final_answer(
                content,
                skip_thinking=skip_thinking,
            )
            input_tokens, output_tokens = _extract_usage(completion)
            return ChatCompletionResult(
                content=content,
                provider_response_id=getattr(completion, "id", None),
                model=getattr(completion, "model", None),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=finish_reason,
            )
        except (TypeError, ValueError) as error:
            raise LlmResponseError(str(error)) from None

    def stream_chat_completion(
        self,
        *,
        messages: Sequence[Mapping[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        skip_thinking: bool = False,
    ) -> Any:
        """실시간 토큰 스트리밍 제너레이터를 반환한다."""
        if not 0 <= temperature <= 2:
            raise ValueError("temperature는 0 이상 2 이하여야 합니다.")

        if max_tokens <= 0:
            raise ValueError("max_tokens는 0보다 커야 합니다.")

        normalized_messages = _normalize_messages(messages)

        if skip_thinking:
            normalized_messages.append(
                {
                    "role": "assistant",
                    "content": THINKING_COMPLETED_PREFILL,
                }
            )

        arguments: dict[str, Any] = {
            "model": self._settings.model,
            "messages": normalized_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            response = self._sdk_client.chat.completions.create(**arguments)
            in_thinking_block = False
            for chunk in response:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue
                content = getattr(delta, "content", None)
                if not content:
                    continue

                if skip_thinking:
                    if "<think>" in content:
                        in_thinking_block = True
                        continue
                    if "</think>" in content:
                        in_thinking_block = False
                        continue
                    if in_thinking_block:
                        continue

                yield content
        except (APIConnectionError, APITimeoutError) as error:
            raise LlmTransportError(
                f"LLM 스트리밍 연결 오류 또는 타임아웃: {type(error).__name__}"
            ) from None
        except APIStatusError as error:
            raise LlmTransportError(
                f"LLM 스트리밍 HTTP 오류: status_code={error.status_code}"
            ) from None
        except Exception as error:
            raise LlmClientError(
                f"LLM 스트리밍 중 오류 발생: {type(error).__name__}"
            ) from None

    def _create_completion(self, arguments: dict[str, Any]) -> Any:
        delays = (1.0, 2.0)

        for attempt in range(3):
            try:
                return self._sdk_client.chat.completions.create(**arguments)
            except (APIConnectionError, APITimeoutError) as error:
                if attempt == 2:
                    raise LlmTransportError(
                        "LLM 연결 요청이 3회 실패했습니다: "
                        f"{type(error).__name__}"
                    ) from None
            except APIStatusError as error:
                if not _is_retryable_status(error.status_code):
                    raise LlmTransportError(
                        "재시도하지 않는 LLM HTTP 오류입니다: "
                        f"status_code={error.status_code}"
                    ) from None

                if attempt == 2:
                    raise LlmTransportError(
                        "LLM HTTP 요청이 3회 실패했습니다: "
                        f"status_code={error.status_code}"
                    ) from None
            except Exception as error:
                raise LlmClientError(
                    "LLM SDK에서 예상하지 못한 오류가 발생했습니다: "
                    f"{type(error).__name__}"
                ) from None

            self._sleep(delays[attempt])

        raise AssertionError("LLM 재시도 루프가 결과 없이 종료됐습니다.")


def _extract_final_answer(
    content: str,
    *,
    skip_thinking: bool,
) -> str:
    """assistant prefill의 think 블록을 제거하고 최종 답변만 남긴다."""
    cleaned_content = content.strip()

    if not skip_thinking:
        return cleaned_content

    if "</think>" in cleaned_content:
        cleaned_content = cleaned_content.split(
            "</think>",
            1,
        )[1].strip()
    elif "<think>" in cleaned_content:
        raise LlmResponseError(
            "LLM 생각 과정이 닫히지 않아 최종 답변을 확인할 수 없습니다."
        )

    cleaned_content = cleaned_content.replace(
        "<think>",
        "",
    ).replace(
        "</think>",
        "",
    ).strip()

    if not cleaned_content:
        raise LlmResponseError(
            "LLM 응답에 사용자에게 표시할 최종 답변이 없습니다."
        )

    return cleaned_content


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 429} or status_code >= 500
