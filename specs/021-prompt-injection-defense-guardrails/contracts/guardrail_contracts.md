# Guardrail Service Contracts & Security Interfaces

**Feature**: `021-prompt-injection-defense-guardrails`

## 1. Python Class Interface Contract (`bteam/oliview_core/guardrail.py`)

```python
class PromptInjectionGuardrail:
    """Multi-tiered Defense-in-Depth Prompt Injection Guardrail Engine."""

    SAFE_BLOCKED_RESPONSE: str = (
        "올리뷰는 올리브영 화장품 리뷰 분석 전용 AI입니다. "
        "시스템 지침 변경이나 관련 없는 요청에는 답변할 수 없습니다. "
        "궁금하신 화장품에 대해 질문해 주세요! 🌿"
    )

    @classmethod
    def deobfuscate_text(cls, text: str) -> str:
        """Removes zero-width characters and normalizes unicode homoglyphs."""
        ...

    @classmethod
    def detect_injection(cls, text: str) -> InjectionDetectionResult:
        """
        Executes Tier 1 deterministic regex signature detection.
        Returns InjectionDetectionResult with is_blocked=True if threat is detected.
        Guaranteed execution time: <10ms.
        """
        ...

    @classmethod
    def sanitize_xml_tags(cls, text: str) -> str:
        """Escapes XML/HTML tags in user input to prevent sandbox breakout."""
        ...

    @classmethod
    def build_sandboxed_rag_prompt(
        cls,
        user_query: str,
        reference_blocks: List[str],
        base_system_prompt: str,
    ) -> SandboxedPromptPayload:
        """
        Constructs Tier 2 sandboxed prompt with XML tags, canary token,
        and bottom instruction defense.
        """
        ...

    @classmethod
    def verify_output_safety(
        cls,
        output_chunk: str,
        canary_token: str
    ) -> Tuple[bool, str]:
        """
        Tier 4 Output Guardrail: Detects canary leakage or system prompt extraction.
        Returns (is_safe, sanitized_chunk).
        """
        ...
```

---

## 2. Invariant Security Contracts

1. **Deterministic Defense Invariant**: 알려진 탈옥(DAN, Developer Mode) 및 지침 무시 패턴이 포함된 입력은 LLM 추론 단계에 도달하기 전에 무조건 `is_blocked=True`로 차단되어야 한다.
2. **Zero False Positive Invariant**: 일상적인 화장품 리뷰 관련 질문("자극을 무시할 수 없을 정도로 심한가요?", "피부 진정 시스템이 뭔가요?")은 차단되지 않고 통과해야 한다.
3. **Canary Leakage Invariant**: LLM 출력 스트림에 `canary_token` 문자열이 1글자라도 포함될 경우, 해당 청크는 즉시 안전 안내 문구로 대체되어야 한다.
4. **Latency Budget Invariant**: Tier 1 사전 가드레일(`detect_injection`)의 p99 지연시간은 $10\text{ms}$를 초과하지 않아야 한다.
