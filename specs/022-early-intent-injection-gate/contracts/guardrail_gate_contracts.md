# Interface Contracts: Early Intent & Prompt Guard Gate

**Feature Branch**: `022-early-intent-injection-gate`
**Date**: 2026-08-19

## Python Class Contract: `EarlyIntentGuardrail`

```python
class EarlyIntentGuardrail:
    """
    선제적 하이브리드 의도 및 보안 게이트웨이 (Step 0 조기 차단 엔진)
    """

    SAFE_BEAUTY_REFUSAL: str = (
        "올리뷰는 올리브영 화장품 리뷰 분석 및 뷰티 상담 전용 AI입니다. "
        "시스템 지침 변경이나 관련 없는 요청에는 답변할 수 없습니다. "
        "궁금하신 화장품에 대해 질문해 주세요! 🌿"
    )

    SAFE_MEDICAL_REFUSAL: str = (
        "의약품의 무단 배합이나 불법 제조는 심각한 피부 손상을 유발할 수 있습니다. "
        "정확한 치료 및 처방은 피부과 전문의와 상담해 주세요! 🩺"
    )

    @classmethod
    def evaluate_gate(
        cls,
        query: str,
        client_ip: Optional[str] = None,
        session_id: Optional[str] = None,
        use_cache: bool = True
    ) -> EarlyGateDecision:
        """
        질의 수신 즉시 DB 연결 및 리랭킹 전에 종합 판정을 수행하는 메인 진입점.
        1. NULL 바이트 및 제어문자 살균 & 한글 자모 복원
        2. Redis 보안 캐시 조회
        3. Tier 1A ReDoS-safe 규칙 엔진 (<1ms)
        4. Tier 1B Llama Prompt Guard 86M 로컬 모델 (~15ms)
        5. PII 마스킹 및 감사 로깅
        """
        ...

    @classmethod
    def sanitize_raw_input(cls, text: str) -> str:
        """NULL 바이트(\x00) 및 비가시 C0/C1 제어 문자 100% 제거 및 NFC 복원"""
        ...

    @classmethod
    def is_metaphorical_beauty_query(cls, text: str) -> bool:
        """코딩/게임 등 비도메인 어휘가 섞여 있어도 실제 뷰티 상담인 경우 오탐 없이 True 반환"""
        ...

    @classmethod
    def evaluate_llama_prompt_guard(cls, text: str) -> Tuple[str, float]:
        """로컬 86M Llama Prompt Guard 모델 추론 (BENIGN / INJECTION / JAILBREAK)"""
        ...
```

---

## FastAPI / Streamlit Orchestrator Contract

### 1. Chatbot A (`pipeline.py`)
```python
def prepare_pipeline_stream(question: str, callback=None, category_hint=None):
    # Step 0: Early Gate Check
    decision = EarlyIntentGuardrail.evaluate_gate(question)
    if decision.is_blocked:
        exec_meta = RagExecutionMetadata(
            model_name="guardrail-early-blocked",
            selected_review_count=0,
            reference_reviews=[],  # 무관한 참조 리뷰 원문 노출 0건
            total_latency_sec=decision.latency_ms / 1000.0
        )
        return _blocked_stream(decision.refusal_message), exec_meta

    # Step 1 ~ 3: Normal RAG Pipeline
    ...
```

### 2. Chatbot B (`project_ragapi.py`)
```python
@app.post("/api/v1/search", response_model=RagSearchResponse)
def search_products_with_rag(request_body: SearchRequest):
    # Step 0: Early Gate Check (Before DB Connection!)
    decision = EarlyIntentGuardrail.evaluate_gate(request_body.query)
    if decision.is_blocked:
        return RagSearchResponse(
            llm_answer=decision.refusal_message,
            search_results=[],  # DB 검색 0회, 결과 0개
            model_used="guardrail-early-blocked"
        )

    # Step 1 ~ 3: Normal DB Connection & RAG Pipeline
    ...
```
