# Interface Contracts: 012-restore-pilos-pipeline

**Feature**: [`012-restore-pilos-pipeline`](file:///c:/AISERVICE/specs/012-restore-pilos-pipeline/spec.md)  
**Date**: 2026-08-19  
**Status**: Specified  

---

## 1. 수급 수집 작업 인터페이스 (`collect_supply_demand.py`)

### 1.1 `run_supply_demand_collection` 함수 계약
```python
def run_supply_demand_collection(
    *,
    now: datetime | None = None,
) -> JobResult:
    """
    현재 시각(KST)을 기준으로 수급 데이터 수집(추정/확정)을 실행한다.

    Returns:
        JobResult:
            - status: JobStatus.COMPLETED | JobStatus.SKIPPED
            - reason_code:
                * JobReason.ESTIMATE_COMPLETED (장중 추정 완료)
                * JobReason.CONFIRM_COMPLETED (장 마감 확정 완료)
                * JobReason.NO_CREDENTIALS (키움 API Key 부재로 안전 스킵)
                * JobReason.API_UNAVAILABLE (외부 API 통신 장애로 안전 스킵)
                * JobReason.BEFORE_MARKET / WAITING_FINAL_DATA / WEEKEND (시간대 스킵)
            - processed_count: 처리된 종목 건수
            - message: 처리 요약 또는 스킵 사유
    """
```

---

## 2. 최상위 서비스 파이프라인 인터페이스 (`run_service_pipeline.py`)

### 2.1 `run_service_pipeline` 실행 계약
```python
def run_service_pipeline(
    *,
    target: str | None = None,
    now: datetime | None = None,
) -> PipelineRunSummary:
    """
    7개 단계를 순차 실행한다:
    1. comment_collection
    2. comment_preprocessing
    3. comment_tokenization
    4. daily_document
    5. supply_demand (Graceful Fallback: SKIPPED 상태 시 정상 속행)
    6. model_inference (8/12 이후 누락분 포함 추론)
    7. llm_report (qwen3.5-2b 기반 시장 해설 생성)

    Returns:
        PipelineRunSummary:
            - status: "completed" | "failed"
            - stages: dict[str, StageResult]
            - elapsed_seconds: float
    """
```

---

## 3. LLM 보고서 생성 및 소급 실행 계약 (`generate_llm_reports.py`)

### 3.1 CLI 실행 인터페이스
```bash
# 8월 12일부터 현재까지의 누락 보고서 일괄 소급 생성
python -m pilos.jobs.generate_llm_reports --start-date 2026-08-12 --end-date 2026-08-19
```

### 3.2 반환 및 집계 계약
```python
{
    "input_count": 80,          # 대상 종목*일자 총합
    "generated_count": 80,      # 신규 생성 성공 건수
    "deterministic_count": 0,   # 정형 수치 기본 요약 건수
    "existing_count": 0,        # 기존 완료 스킵 건수
    "updated_count": 0,         # 갱신 건수
    "not_ready_count": 0,       # 미준비 건수
    "failed_count": 0           # 실패 건수
}
```

---

## 4. 모델 서빙 게이트웨이 인터페이스 (`model_gateway`)

### 4.1 OpenAI 호환 요청 계약
```http
POST /v1/chat/completions HTTP/1.1
Host: vllm-serv-gateway:8081
Content-Type: application/json

{
  "model": "qwen3.5-2b",
  "messages": [
    {
      "role": "system",
      "content": "당신은 금융 시장 분석 전문가입니다."
    },
    {
      "role": "user",
      "content": "<신호 요약 및 키워드 데이터>"
    }
  ],
  "temperature": 0.2,
  "max_tokens": 1024
}
```

### 4.2 응답 계약
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "qwen3.5-2b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"market_commentary\": \"...\", \"direction\": \"BULLISH\", ...}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 420,
    "completion_tokens": 310,
    "total_tokens": 730
  }
}
```
