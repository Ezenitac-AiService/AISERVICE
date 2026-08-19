# Technical Research: 챗봇 A/B 런타임 결함 해결 및 vLLM 서빙 게이트웨이 OOM 방어·자가 복구

**Feature**: `024-chatbot-gateway-stability-fix`
**Date**: 2026-08-20

---

## 1. 챗봇 A & B `is_9b` NameError 근본 원인 및 해결

### Decision
`bteam/Oliview_chatbot_a/llm_common.py` 및 `bteam/Oliview_chatbot_b/common.py`의 `budget_context_documents()` 함수 최상단에 `is_9b = "9b" in str(model_name).lower()`를 명시적으로 선언한다.

### Rationale
- **기존 버그 분석**:
  ```python
  # 기존 코드 (Oliview_chatbot_b/common.py L358)
  def budget_context_documents(products: list, model_name: str = "qwen3.5-4b", ...):
      ...
      for p in products:
          # is_9b 선언 없이 바로 조건문 평가 -> NameError 발생!
          if is_9b and len(sentence) > max_sentence_len:
              sentence = sentence[:max_sentence_len - 3] + "..."
  ```
- **개선 방안**:
  함수 시작 지점에서 `is_9b = "9b" in str(model_name).lower()` 및 `max_sentence_len`을 명확히 초기화하여 어떤 인자가 넘어오더라도 예외 없이 안전하게 동작하도록 보장.

---

## 2. vLLM 서빙 게이트웨이 OOM 서브프로세스 감지 및 즉시 자가 치유(Self-Healing)

### Decision
`model_gateway/src/process_manager.py` (또는 `model_gateway/src/api/server.py`)에서 포트 8089 서브프로세스가 OOM Killer (Exit Code 137 / -9)로 비정상 종료되었을 때, 이를 즉시 감지하여 3초 이내에 백그라운드에서 자동 재기동(Auto-Restart)하고 헬스체크를 복원한다.

### Rationale
- Pilos 파이프라인에서 10개 종목의 리포트를 생성할 때 대용량 프롬프트 연산으로 순간적인 VRAM/RAM 피크가 발생하여 서브프로세스가 강제 종료될 수 있음.
- 게이트웨이가 프로세스 종료를 방치하면 이후 챗봇의 모든 요청이 `503 Service Unavailable`로 영구 실패함.
- `ProcessManager`가 요청 프록시 직전에 서브프로세스 생존 상태(`proc.poll() is None`)를 확인하고, 죽어있으면 즉시 재기동(`ensure_server_running()`)함으로써 자가 복구 능력 확보.

---

## 3. 챗봇 클라이언트 단 일시적 장애 재시도(Exponential Backoff Retry)

### Decision
`bteam/Oliview_chatbot_a/llm_common.py`의 `create_chat_completion_with_fallback()` 및 `bteam/Oliview_chatbot_b/project_ragapi.py`의 LLM 호출부에 503/502/ConnectionError 발생 시 최대 2회 (1초 대기) 자동 재시도 로직을 적용한다.

### Rationale
- 게이트웨이 서브프로세스가 재기동되는 2~3초의 짧은 시간 동안 들어온 챗봇 요청이 즉시 에러로 터지지 않고, 재시도를 통해 정상 답변을 생성하여 사용자 경험을 보호.

---

## 4. 프롬프트 캐시 상태 저장 OOM 방지 튜닝

### Decision
`vllm-serv` 서브프로세스 구동 시 `llama-cpp-python`의 과도한 메모리 점유를 유발하는 state write / KV cache allocation 오버헤드를 방지하도록 컨텍스트 윈도우 및 배치 사이즈를 안전한 한도로 고정.
