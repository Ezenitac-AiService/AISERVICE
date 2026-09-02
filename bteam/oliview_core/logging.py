"""
Structured Privacy-Preserving Logger (Spec 048 / Constitution Principle IV).
"""

import datetime
import json
import logging
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("oliview.structured")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(message)s"))
if not logger.handlers:
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

PROHIBITED_RAW_FIELDS = {"query", "review", "reviews", "prompt", "token", "tokens", "password", "secret", "bearer"}


def emit_structured_log(
    correlation_id: str,
    service: str,
    event: str,
    latency_ms: int = 0,
    model_invoked: bool = False,
    abstained: bool = False,
    redaction_applied: bool = False,
    guardrail_counts: Optional[Dict[str, int]] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Emits structured log JSON. Strict privacy preservation: raw user/review data prohibited."""
    counts = {
        "persona_removed": 0,
        "quotes_removed": 0,
        "citations_removed": 0,
        "polarity_blocked": 0,
        "injection_blocked": 0,
        "pii_redacted": 0,
    }
    if guardrail_counts:
        counts.update(guardrail_counts)

    log_entry: Dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "service": service,
        "event": event,
        "latency_ms": max(0, latency_ms),
        "model_invoked": model_invoked,
        "abstained": abstained,
        "redaction_applied": redaction_applied,
        "guardrail_counts": counts,
    }

    if extra_meta:
        for k, v in extra_meta.items():
            if k.lower() in PROHIBITED_RAW_FIELDS:
                raise ValueError(f"Prohibited sensitive field '{k}' cannot be logged.")
            log_entry[k] = v

    logger.info(json.dumps(log_entry, ensure_ascii=False))
    return log_entry
