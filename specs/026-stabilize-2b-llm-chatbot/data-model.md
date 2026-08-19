# Data Model & Schema Definitions: 026-stabilize-2b-llm-chatbot

## 1. Serving Configuration Entity

```python
class GatewayServingModeConfig:
    """Model Gateway의 서빙 모드 및 상주 모델 설정."""
    single_model_mode: bool = True               # True: 2B 단일 상주 고정, False: 다중 모델 핫스왑 허용
    resident_model_id: str = "qwen3.5-2b"        # 기본 상주 모델 ID
    resident_n_ctx: int = 16384                  # 2B 모델 컨텍스트 윈도우 크기 (16K)
    enable_flash_attn: bool = False              # Pascal (GTX 1070) 안정성을 위한 Flash-Attn 폴백 제어
```

---

## 2. Hybrid Token Budget Policy Entity

```python
class HybridTokenBudgetPolicy:
    """작업 목적별 3단계 토큰 예산 정책."""
    fast_intent_max_tokens: int = 512            # 의도분류 및 메타데이터 필터링 (0.5s 이내)
    standard_rag_max_tokens: int = 2048          # 대화형 뷰티 솔루션 생성 (1,000~1,500자 완결)
    deep_report_max_tokens: int = 4096           # 전수 비교 및 Pilos 시장 코멘터리 장문 리포트
```

---

## 3. Inference Request & Response Schema

```python
class UnifiedChatCompletionRequest:
    model: str = "qwen3.5-2b"                    # 단일 모델 모드에서는 게이트웨이에서 자동 보정
    messages: list[dict[str, str]]               # System/User 대화 메시지
    max_tokens: int = 2048                       # 작업별 토큰 예산
    temperature: float = 0.3                     # RAG 사실성 보장을 위한 낮은 온도
    stream: bool = True                          # SSE 스트리밍 플래그
```

---

## 4. Guardrail Safety Assessment Entity

```python
class SecurityVerificationResult:
    is_safe: bool                                # 안전성 검증 통과 여부
    canary_intact: bool                          # 카나리 토큰 누출 여부
    matched_rule: str | None = None              # 탐지된 규칙 명칭
    sanitized_text: str | None = None            # 정제된 안전 텍스트
```
