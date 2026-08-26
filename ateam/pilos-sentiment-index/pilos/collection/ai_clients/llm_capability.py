import os

from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from pilos.collection.ai_clients.llm_report_client import (
    ReportOutputMode,
    SUPPORTED_OUTPUT_MODES,
    build_report_response_format,
    parse_market_commentary_response,
)
from pilos.dto.llm_report_dto import (
    LlmCapabilityCheckResult,
)

CAPABILITY_SYSTEM_PROMPT = (
    "당신은 한국어 분석 보고서를 JSON으로 작성하는 도우미입니다. "
    "내부 사고 과정, <think> 태그, 마크다운 코드 펜스와 설명 문장을 "
    "출력하지 말고 요청된 JSON 객체만 반환하세요."
)
CAPABILITY_USER_PROMPT = (
    "서버 구조화 출력 기능 확인용으로 다음 두 필드를 가진 짧은 "
    "한국어 JSON 보고서를 작성하세요: market_commentary, conclusion."
)
BASIC_CHAT_PROMPT = (
    "서버 연결 확인을 위해 한국어로 한 문장만 답변하세요."
)


@dataclass(frozen=True, slots=True)
class LlmCapabilitySettings:
    """DB를 사용하지 않는 LLM capability 점검 환경설정이다."""

    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "LlmCapabilitySettings":
        """로컬 환경변수에서 필수 capability 설정을 읽어 검증한다."""
        load_dotenv()

        values = {
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "").strip(),
            "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "").strip(),
            "LLM_API_KEY": os.getenv("LLM_API_KEY", "").strip(),
            "REPORT_LLM_MODEL": os.getenv(
                "REPORT_LLM_MODEL",
                "",
            ).strip(),
        }
        missing_names = [
            name
            for name, value in values.items()
            if not value
        ]

        if missing_names:
            raise ValueError(
                "LLM capability 필수 환경변수가 비어 있습니다: "
                f"{missing_names}"
            )

        base_url = values["LLM_BASE_URL"].rstrip("/")

        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                "LLM_BASE_URL은 http:// 또는 https://로 시작해야 합니다."
            )

        timeout_text = os.getenv(
            "REPORT_LLM_TIMEOUT_SECONDS",
            "60",
        ).strip()

        try:
            timeout_seconds = float(timeout_text)
        except ValueError as error:
            raise ValueError(
                "REPORT_LLM_TIMEOUT_SECONDS는 숫자여야 합니다."
            ) from error

        if timeout_seconds <= 0:
            raise ValueError(
                "REPORT_LLM_TIMEOUT_SECONDS는 0보다 커야 합니다."
            )

        return cls(
            provider=values["LLM_PROVIDER"],
            base_url=base_url,
            api_key=values["LLM_API_KEY"],
            model=values["REPORT_LLM_MODEL"],
            timeout_seconds=timeout_seconds,
        )


def create_openai_compatible_client(
    settings: LlmCapabilitySettings,
) -> OpenAI:
    """자동 재시도 없이 OpenAI 호환 capability 점검 클라이언트를 만든다."""
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        max_retries=0,
    )


def _sanitize_error_message(
    error: Exception,
    settings: LlmCapabilitySettings,
) -> str:
    """오류 메시지에서 API 키를 제거하고 보고 길이를 제한한다."""
    message = str(error)

    if settings.api_key:
        message = message.replace(settings.api_key, "***")

    return message[:500]


def _optional_int(value: Any) -> int | None:
    """공급자가 선택적으로 반환하는 토큰 수를 정수 또는 None으로 만든다."""
    if value is None:
        return None

    return int(value)


def _extract_usage(completion: Any) -> tuple[int | None, int | None]:
    """SDK usage가 없거나 일부 필드가 빠진 응답을 nullable 값으로 바꾼다."""
    usage = getattr(completion, "usage", None)

    if usage is None:
        return None, None

    return (
        _optional_int(getattr(usage, "prompt_tokens", None)),
        _optional_int(getattr(usage, "completion_tokens", None)),
    )


def _completion_to_result(
    *,
    check_name: str,
    completion: Any,
) -> LlmCapabilityCheckResult:
    """Chat Completions 응답을 검증해 공급자 중립 점검 결과로 바꾼다."""
    choices = getattr(completion, "choices", None)

    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("LLM 응답 choices는 정확히 한 건이어야 합니다.")

    choice = choices[0]
    message = getattr(choice, "message", None)
    refusal = getattr(message, "refusal", None)

    if refusal:
        raise ValueError("LLM이 보고서 생성을 거절했습니다.")

    finish_reason = getattr(choice, "finish_reason", None)
    narrative = parse_market_commentary_response(
        content=getattr(message, "content", None),
        finish_reason=finish_reason,
    )
    input_tokens, output_tokens = _extract_usage(completion)

    # capability 확인에서는 서술 내용을 출력하거나 저장하지 않는다.
    _ = narrative

    return LlmCapabilityCheckResult(
        check_name=check_name,
        success=True,
        provider_response_id=getattr(completion, "id", None),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_reason=finish_reason,
    )


def probe_models(
    *,
    client: Any,
    settings: LlmCapabilitySettings,
) -> LlmCapabilityCheckResult:
    """실제 서버가 공개하는 모델 ID 목록을 공급자 중립 결과로 반환한다."""
    try:
        models = client.models.list()
        model_ids = tuple(
            sorted(
                str(model.id)
                for model in getattr(models, "data", [])
                if getattr(model, "id", None)
            )
        )

        if not model_ids:
            raise ValueError("서버가 모델 ID를 한 건도 반환하지 않았습니다.")

        return LlmCapabilityCheckResult(
            check_name="models",
            success=True,
            model_ids=model_ids,
        )
    except Exception as error:
        return LlmCapabilityCheckResult(
            check_name="models",
            success=False,
            error_type=type(error).__name__,
            error_message=_sanitize_error_message(error, settings),
        )


def probe_report_output_mode(
    *,
    client: Any,
    settings: LlmCapabilitySettings,
    output_mode: ReportOutputMode,
) -> LlmCapabilityCheckResult:
    """출력 모드 하나를 실제 Chat Completions 요청으로 독립 점검한다."""
    request_arguments: dict[str, Any] = {
        "model": settings.model,
        "messages": [
            {
                "role": "system",
                "content": CAPABILITY_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": CAPABILITY_USER_PROMPT,
            },
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    response_format = build_report_response_format(output_mode)

    if response_format is not None:
        request_arguments["response_format"] = response_format

    try:
        completion = client.chat.completions.create(
            **request_arguments,
        )

        return _completion_to_result(
            check_name=output_mode,
            completion=completion,
        )
    except Exception as error:
        return LlmCapabilityCheckResult(
            check_name=output_mode,
            success=False,
            error_type=type(error).__name__,
            error_message=_sanitize_error_message(error, settings),
        )


def probe_basic_chat(
    *,
    client: Any,
    settings: LlmCapabilitySettings,
) -> LlmCapabilityCheckResult:
    """구조화 옵션 없이 기본 한국어 Chat Completions를 점검한다."""
    try:
        completion = client.chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "user",
                    "content": BASIC_CHAT_PROMPT,
                }
            ],
            temperature=0.3,
            max_tokens=128,
        )
        choices = getattr(completion, "choices", None)

        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError(
                "LLM 응답 choices는 정확히 한 건이어야 합니다."
            )

        choice = choices[0]
        finish_reason = getattr(choice, "finish_reason", None)

        if finish_reason != "stop":
            raise ValueError(
                "기본 Chat 응답이 정상 종료되지 않았습니다: "
                f"finish_reason={finish_reason}"
            )

        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)

        if (
            not isinstance(content, str)
            or not content.strip()
            or not any("가" <= char <= "힣" for char in content)
        ):
            raise ValueError(
                "기본 Chat 응답에 한국어 본문이 없습니다."
            )

        input_tokens, output_tokens = _extract_usage(completion)

        return LlmCapabilityCheckResult(
            check_name="basic_chat",
            success=True,
            provider_response_id=getattr(completion, "id", None),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=finish_reason,
        )
    except Exception as error:
        return LlmCapabilityCheckResult(
            check_name="basic_chat",
            success=False,
            error_type=type(error).__name__,
            error_message=_sanitize_error_message(error, settings),
        )


def run_llm_capability_probes(
    *,
    settings: LlmCapabilitySettings,
    client: Any | None = None,
) -> list[LlmCapabilityCheckResult]:
    """모델 목록과 네 출력 모드를 서로 fallback하지 않고 모두 점검한다."""
    if client is None:
        client = create_openai_compatible_client(settings)

    results = [
        probe_models(
            client=client,
            settings=settings,
        ),
        probe_basic_chat(
            client=client,
            settings=settings,
        ),
    ]

    for output_mode in SUPPORTED_OUTPUT_MODES:
        results.append(
            probe_report_output_mode(
                client=client,
                settings=settings,
                output_mode=output_mode,
            )
        )

    return results
