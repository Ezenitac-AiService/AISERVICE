# Data Model: 챗봇 A/B 런타임 안정성 및 vLLM 서빙 게이트웨이 복원 모델

**Feature**: `024-chatbot-gateway-stability-fix`
**Date**: 2026-08-20

---

## 1. Entities

### 1.1 ContextTrimmingBudget (컨텍스트 예산 제어 모델)
챗봇 A/B의 프롬프트 주입 전 문서 길이 및 개별 문장 길이를 제한하는 메모리 모델.

| Field | Type | Default | Description |
| :--- | :--- | :---: | :--- |
| `model_name` | `str` | `"qwen3.5-4b"` | 호출 대상 모델명 |
| `is_9b` | `bool` | `False` | 9B 계열 모델 여부 판별 플래그 |
| `max_budget_chars`| `int` | `1500` | 전체 문서 컨텍스트 최대 글자 수 |
| `max_sentence_len`| `int` | `150` | 개별 문장 최대 길이 (9B일 때 150자 트리밍) |

---

### 1.2 SubprocessHealthStatus (게이트웨이 서브프로세스 헬스 상태)

| Field | Type | Description |
| :--- | :--- | :--- |
| `port` | `int` | 서브프로세스 바인딩 포트 (예: `8089`) |
| `pid` | `int` | 운영체제 프로세스 ID |
| `is_alive` | `bool` | 프로세스 생존 여부 (`poll() is None`) |
| `restart_count` | `int` | OOM 또는 크래시 후 재기동 누적 횟수 |
| `last_exit_code` | `int` | 마지막 종료 코드 (예: `-9`, `137` = OOM) |

---

### 1.3 RetryPolicy (챗봇 LLM 호출 재시도 정책)

| Field | Type | Value | Description |
| :--- | :--- | :---: | :--- |
| `max_retries` | `int` | `2` | 최대 재시도 횟수 |
| `backoff_factor` | `float` | `1.0` | 재시도 대기 간격 (초) |
| `retryable_status_codes` | `list[int]` | `[502, 503, 504]` | 자동 재시도 대상 HTTP 상태 코드 |
