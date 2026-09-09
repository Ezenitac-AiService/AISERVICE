import json

from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo

from pilos.collection.ai_clients.llm_capability import run_llm_capability_probes
from pilos.collection.ai_clients.llm_client import LlmClientSettings


# CLI: uv run python -m pilos.jobs.check_llm_capabilities

KST = ZoneInfo("Asia/Seoul")

def run_llm_capability_check(
    *,
    settings: LlmClientSettings | None = None,
    executed_at: datetime | None = None
) -> dict:
    """DB 없이 설정한 LLM 서버의 모델 목록과 기본 Chat을 점검한다."""
    if settings is None:
        settings = LlmClientSettings.from_env()

    checked_at = executed_at or datetime.now(KST)
    if checked_at.tzinfo is None:
        raise ValueError("executed_at은 timezone 정보가 필요합니다.")

    results = run_llm_capability_probes(settings=settings)
    return {
        "provider": settings.provider,
        "model": settings.model,
        "executed_at": checked_at.astimezone(KST).isoformat(timespec="seconds"),
        "checks": [asdict(result) for result in results],
        "success_count": sum(result.success for result in results),
        "failed_count": sum(not result.success for result in results),
    }


def main() -> None:
    """비밀값을 제외한 capability 결과를 JSON으로 출력한다."""
    summary = run_llm_capability_check()
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )
    if summary["failed_count"] > 0:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
