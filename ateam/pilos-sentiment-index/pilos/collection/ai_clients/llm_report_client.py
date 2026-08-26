import json
import os
import time

from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
)

from pilos.analysis.llm_report import (
    build_report_messages,
    validate_market_commentary_response,
)
from pilos.dto.llm_report_dto import (
    LlmMarketCommentary,
    ReportGenerationRequest,
    ReportGenerationResult,
)


ReportOutputMode = Literal[
    "json_schema",
    "json_schema_strict",
    "json_object",
    "prompt_json",
]
SUPPORTED_OUTPUT_MODES: tuple[ReportOutputMode, ...] = (
    "json_schema",
    "json_schema_strict",
    "json_object",
    "prompt_json",
)

# 생성 설정이다. 프롬프트 실험이 production과 같은 조건에서 이뤄지도록
# 상수로 노출한다.
REPORT_TEMPERATURE = 0.25
REPORT_MAX_TOKENS = 2048  # Spec 035: 16K/32K 대용량 컨텍스트 확장에 따라 1400 -> 2048 기본 상향


class PilosExecutionHarness:
    """16K/32K 대용량 컨텍스트 환경에서 30~60건의 뉴스/커뮤니티 데이터를 일괄 주입하는 실행 하네스 (Spec 035 FR-007)."""

    @staticmethod
    def package_batch_prompt(
        documents: list[dict[str, Any]],
        instruction: str = "시장 감성 지수를 종합 분석하세요."
    ) -> str:
        doc_parts = [f'<market_documents total_count="{len(documents)}">']
        for idx, doc in enumerate(documents, start=1):
            title = doc.get("title", "")
            content = doc.get("content", "")
            date = doc.get("date", "")
            source = doc.get("source", "")
            doc_parts.append(f'  <doc id="{idx}" date="{date}" source="{source}">')
            doc_parts.append(f'    <title>{title}</title>')
            doc_parts.append(f'    <content>{content}</content>')
            doc_parts.append('  </doc>')
        doc_parts.append('</market_documents>')
        doc_parts.append(f"\n{instruction}")
        return "\n".join(doc_parts)


def load_llm_report_identity_from_env() -> tuple[str, str]:
    """API 비밀값을 요구하지 않고 보고서 생성 고유키 식별값만 읽는다."""
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "openai").strip()
    model = (os.getenv("REPORT_LLM_MODEL") or os.getenv("FAST_LLM_MODEL") or "qwen3.5-2b").strip()
    return provider, model


@dataclass(frozen=True, slots=True)
class LlmCompletion:
    """
    공급자 SDK 형식을 제거한 단일 생성 결과다.

    파싱과 검증 이전 단계의 원문을 그대로 담는다. 프롬프트 실험이 같은
    호출 경로를 재사용하면서 원문을 확인할 수 있어야 하기 때문이다.
    """

    content: str | None
    finish_reason: str | None
    response_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    refusal: str | None = None


class RejectionObserver(Protocol):
    """
    검증에서 거부된 시도를 그때마다 통보받는 관찰자다.

    재시도 후 성공하면 첫 시도의 원문이 사라져 규칙이 과했는지 확인할 수
    없다. 클라이언트는 기록 방법을 모른 채 시도마다 알리기만 하고, 실제
    기록은 실행 계층인 jobs가 담당한다.
    """

    def __call__(
        self,
        *,
        attempt: int,
        commentary: LlmMarketCommentary | None,
        reason: str,
    ) -> None:
        ...


class LlmReportClient(Protocol):
    """jobs가 공급자 SDK를 모르고 보고서를 생성하게 하는 공개 경계다."""

    def generate_report(
        self,
        request: ReportGenerationRequest,
        *,
        on_rejection: "RejectionObserver | None" = None,
    ) -> ReportGenerationResult:
        """검증된 요청으로 한국어 시장 코멘터리를 생성한다."""
        ...


class LlmReportClientError(RuntimeError):
    """공급자 SDK 예외를 제거한 보고서 클라이언트 오류다."""


class LlmReportTransportError(LlmReportClientError):
    """재시도 후에도 완료되지 않은 연결 또는 HTTP 오류다."""


class LlmReportResponseError(LlmReportClientError):
    """
    두 번의 생성에서도 해소되지 않은 응답 계약 오류다.

    거부된 응답 본문을 함께 전달한다. 어떤 문장이 왜 걸렸는지 확인해야
    검증 규칙이 과했는지 판단할 수 있는데, 예외 메시지만으로는 원문을
    복원할 수 없기 때문이다. 기록은 실행 계층인 jobs가 담당한다.
    """

    def __init__(
        self,
        message: str,
        *,
        rejected_commentary: LlmMarketCommentary | None = None,
        rejection_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rejected_commentary = rejected_commentary
        self.rejection_reason = rejection_reason


@dataclass(frozen=True, slots=True)
class LlmReportClientSettings:
    """생산용 보고서 클라이언트의 명시적 환경설정이다."""

    provider: str
    base_url: str
    api_key: str
    model: str
    output_mode: ReportOutputMode
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "LlmReportClientSettings":
        """환경변수에서 공급자와 승인된 출력 모드를 읽어 검증한다."""
        load_dotenv()
        provider, model = load_llm_report_identity_from_env()
        names = (
            "LLM_BASE_URL",
            "LLM_API_KEY",
        )
        values = {name: os.getenv(name, "").strip() for name in names}
        output_mode_raw = os.getenv("REPORT_LLM_OUTPUT_MODE", "json_object").strip() or "json_object"
        values["REPORT_LLM_OUTPUT_MODE"] = output_mode_raw
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(
                "LLM 보고서 필수 환경변수가 비어 있습니다: "
                f"{missing}"
            )

        base_url = values["LLM_BASE_URL"].rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                "LLM_BASE_URL은 http:// 또는 https://로 시작해야 합니다."
            )

        output_mode = values["REPORT_LLM_OUTPUT_MODE"]
        if output_mode not in SUPPORTED_OUTPUT_MODES:
            raise ValueError(
                "REPORT_LLM_OUTPUT_MODE가 지원 목록에 없습니다: "
                f"{output_mode}"
            )

        timeout_text = os.getenv("REPORT_LLM_TIMEOUT_SECONDS", "60").strip()
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
            provider=provider,
            base_url=base_url,
            api_key=values["LLM_API_KEY"],
            model=model,
            output_mode=output_mode,
            timeout_seconds=timeout_seconds,
        )


def build_report_response_format(
    output_mode: ReportOutputMode,
) -> dict[str, Any] | None:
    """승인된 모드의 OpenAI 호환 response_format을 만든다."""
    if output_mode not in SUPPORTED_OUTPUT_MODES:
        raise ValueError(f"지원하지 않는 출력 모드입니다: {output_mode}")
    if output_mode == "prompt_json":
        return None
    if output_mode == "json_object":
        return {"type": "json_object"}

    json_schema = {
        "name": "market_commentary",
        "schema": LlmMarketCommentary.model_json_schema(),
    }
    if output_mode == "json_schema_strict":
        json_schema["strict"] = True
    return {"type": "json_schema", "json_schema": json_schema}


def parse_market_commentary_response(
    *,
    content: str,
    finish_reason: str | None,
) -> LlmMarketCommentary:
    """복구 없이 전체 응답 JSON을 시장 코멘터리 DTO로 검증한다."""
    if finish_reason != "stop":
        raise ValueError(
            "LLM 응답이 정상 종료되지 않았습니다: "
            f"finish_reason={finish_reason}"
        )
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM 시장 코멘터리 응답이 비어 있습니다.")

    stripped = content.strip()
    if "<think>" in stripped or "</think>" in stripped:
        raise ValueError("LLM 응답에 <think> 내용이 포함되어 있습니다.")
    if "```" in stripped:
        raise ValueError("LLM 응답에 마크다운 코드 펜스가 포함되어 있습니다.")

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ValueError(
            "LLM 응답 전체를 JSON 객체로 파싱할 수 없습니다."
        ) from error
    if not isinstance(parsed, dict):
        raise ValueError("LLM 시장 코멘터리 JSON은 객체여야 합니다.")
    return LlmMarketCommentary.model_validate(parsed)


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


class OpenAICompatibleLlmReportClient:
    """OpenAI 호환 서버에서 생성하고 내용 오류를 한 번만 교정한다."""

    def __init__(
        self,
        *,
        settings: LlmReportClientSettings,
        sdk_client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._sdk_client = sdk_client or OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )

    def request_completion(
        self,
        messages: list[dict[str, str]],
    ) -> LlmCompletion:
        """
        임의의 메시지로 한 번 생성하고 원문을 그대로 반환한다.

        production 생성과 프롬프트 실험이 같은 호출 경로를 쓰도록 분리한
        경계다. 파싱과 검증은 호출자가 결정한다.
        """
        arguments: dict[str, Any] = {
            "model": self._settings.model,
            "messages": list(messages),
            "temperature": REPORT_TEMPERATURE,
            "max_tokens": REPORT_MAX_TOKENS,
        }
        response_format = build_report_response_format(
            self._settings.output_mode
        )

        if response_format is not None:
            arguments["response_format"] = response_format

        arguments["extra_body"] = {"priority": "low"}

        completion = self._create_completion(arguments)
        choices = getattr(completion, "choices", None)

        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError(
                "LLM 응답 choices는 정확히 한 건이어야 합니다."
            )

        choice = choices[0]
        message = getattr(choice, "message", None)
        input_tokens, output_tokens = _extract_usage(completion)
        return LlmCompletion(
            content=getattr(message, "content", None),
            finish_reason=getattr(choice, "finish_reason", None),
            response_id=getattr(completion, "id", None),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            refusal=getattr(message, "refusal", None),
        )

    def generate_report(
        self,
        request: ReportGenerationRequest,
        *,
        on_rejection: RejectionObserver | None = None,
    ) -> ReportGenerationResult:
        """구조·근거 검증 실패 시 교정 사유를 전달해 한 번 재생성한다."""
        if (
            request.provider != self._settings.provider
            or request.model != self._settings.model
        ):
            raise ValueError(
                "보고서 요청의 provider·model이 클라이언트 설정과 다릅니다."
            )

        base_messages = list(build_report_messages(request))
        last_error: Exception | None = None
        last_commentary: LlmMarketCommentary | None = None

        for content_attempt in range(2):
            messages = list(base_messages)
            if content_attempt == 1:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "이전 응답은 다음 검증에 실패했습니다: "
                            f"{last_error}. 입력 정형 근거와 "
                            "market_commentary·conclusion 두 필드 JSON 계약을 "
                            "지켜 한 번만 다시 작성하세요."
                        ),
                    }
                )
            # 시도마다 초기화한다. 2차에서 파싱이 실패했는데 1차 본문이
            # 남아 있으면 어느 시도의 문장인지 알 수 없게 된다.
            attempt_commentary: LlmMarketCommentary | None = None

            try:
                completion = self.request_completion(messages)

                if completion.refusal:
                    raise ValueError("LLM이 보고서 생성을 거절했습니다.")

                commentary = parse_market_commentary_response(
                    content=completion.content,
                    finish_reason=completion.finish_reason,
                )

                # 검증 실패 시 원문을 남기기 위해 파싱 직후 보관한다.
                attempt_commentary = commentary
                last_commentary = commentary
                validate_market_commentary_response(
                    request=request,
                    response=commentary,
                )
                return ReportGenerationResult(
                    commentary=commentary,
                    provider_response_id=completion.response_id,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                )
            except (ValueError, TypeError) as error:
                last_error = error

                # 재시도로 성공하더라도 이 시도의 원문은 잃지 않는다.
                if on_rejection is not None:
                    on_rejection(
                        attempt=content_attempt + 1,
                        commentary=attempt_commentary,
                        reason=str(error),
                    )

        raise LlmReportResponseError(
            "LLM 시장 코멘터리 응답 검증이 2회 실패했습니다: "
            f"{last_error}",
            rejected_commentary=last_commentary,
            rejection_reason=str(last_error),
        )

    def _create_completion(self, arguments: dict[str, Any]) -> Any:
        delays = (1.0, 2.0)
        for attempt in range(3):
            try:
                return self._sdk_client.chat.completions.create(**arguments)
            except (APIConnectionError, APITimeoutError) as error:
                if attempt == 2:
                    raise LlmReportTransportError(
                        "LLM 연결 요청이 3회 실패했습니다: "
                        f"{type(error).__name__}"
                    ) from None
            except APIStatusError as error:
                if not _is_retryable_status(error.status_code):
                    raise LlmReportTransportError(
                        "재시도하지 않는 LLM HTTP 오류입니다: "
                        f"status_code={error.status_code}"
                    ) from None
                if attempt == 2:
                    raise LlmReportTransportError(
                        "LLM HTTP 요청이 3회 실패했습니다: "
                        f"status_code={error.status_code}"
                    ) from None
            except Exception as error:
                raise LlmReportClientError(
                    "LLM SDK에서 예상하지 못한 오류가 발생했습니다: "
                    f"{type(error).__name__}"
                ) from None
            self._sleep(delays[attempt])

        raise AssertionError("LLM 재시도 루프가 결과 없이 종료됐습니다.")


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 429} or status_code >= 500
