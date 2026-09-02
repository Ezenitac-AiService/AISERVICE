"""
Security & Input Validation Engine (Spec 048 / Constitution Principle VI).
Handles Prompt Injection Detection, PII Redaction, and Effective Operational Caps.
"""

import re
from dataclasses import dataclass
from typing import Dict, Any

# Regex patterns for synthetic PII and credentials
PHONE_PATTERN = re.compile(r"(01[0-9]-?[0-9]{3,4}-?[0-9]{4})")
EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
SECRET_KEY_PATTERN = re.compile(r"(SECRET_TOKEN|Bearer\s+[A-Za-z0-9_\-\.]+)", re.IGNORECASE)

# Injection indicators
INJECTION_INDICATORS = [
    r"system\s*override",
    r"ignore\s*(all\s*)?(previous\s*)?instructions",
    r"reveal\s*(secret\s*)?(system\s*)?prompt",
    r"print\s*(secret\s*)?(system\s*)?instructions",
    r"bypass\s*guardrail",
    r"시스템\s*프롬프트.*출력",
    r"지침.*무시",
    r"규칙.*무시",
]
INJECTION_REGEX = re.compile("|".join(INJECTION_INDICATORS), re.IGNORECASE)


@dataclass
class SecurityInspectionResult:
    is_safe: bool
    injection_detected: bool
    reason: str = ""


def inspect_input_security(text: str) -> SecurityInspectionResult:
    """Inspects text for prompt injection and malicious override patterns."""
    if not text or not isinstance(text, str):
        return SecurityInspectionResult(is_safe=True, injection_detected=False)

    if INJECTION_REGEX.search(text):
        return SecurityInspectionResult(
            is_safe=False,
            injection_detected=True,
            reason="Prompt injection pattern detected in input text."
        )

    return SecurityInspectionResult(is_safe=True, injection_detected=False)


def redact_sensitive_pii(text: str) -> str:
    """Redacts phone numbers, email addresses, and secret credentials from text."""
    if not text or not isinstance(text, str):
        return text

    redacted = PHONE_PATTERN.sub("[전화번호]", text)
    redacted = EMAIL_PATTERN.sub("[이메일]", redacted)
    redacted = SECRET_KEY_PATTERN.sub("[인증정보]", redacted)
    return redacted


def compute_effective_limits(
    client_timeout_ms: int | None,
    server_timeout_cap_ms: int,
    client_output_tokens: int | None,
    server_output_token_cap: int,
) -> Dict[str, int]:
    """Computes effective limits using effective = min(client_request, server_cap)."""
    if client_timeout_ms is not None and client_timeout_ms > 0:
        eff_timeout = min(client_timeout_ms, server_timeout_cap_ms)
    else:
        eff_timeout = server_timeout_cap_ms

    if client_output_tokens is not None and client_output_tokens > 0:
        eff_tokens = min(client_output_tokens, server_output_token_cap)
    else:
        eff_tokens = server_output_token_cap

    return {
        "effective_timeout_ms": eff_timeout,
        "effective_max_output_tokens": eff_tokens,
    }
