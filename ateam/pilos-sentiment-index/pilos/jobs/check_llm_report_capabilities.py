import json

from dataclasses import asdict

from pilos.collection.ai_clients.llm_capability import (
    LlmCapabilitySettings,
    run_llm_capability_probes,
)


# CLI:
# uv run python -m pilos.jobs.check_llm_report_capabilities


def run_llm_report_capability_check(
    *,
    settings: LlmCapabilitySettings | None = None,
) -> dict:
    """DB를 사용하지 않고 설정한 LLM 서버의 보고서 capability를 점검한다."""
    if settings is None:
        settings = LlmCapabilitySettings.from_env()

    results = run_llm_capability_probes(
        settings=settings,
    )

    return {
        "provider": settings.provider,
        "model": settings.model,
        "checks": [
            asdict(result)
            for result in results
        ],
        "success_count": sum(
            result.success
            for result in results
        ),
        "failed_count": sum(
            not result.success
            for result in results
        ),
    }


def main() -> None:
    """명시된 환경의 capability 결과를 비밀값 없이 JSON으로 출력한다."""
    summary = run_llm_report_capability_check()
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
