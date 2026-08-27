from __future__ import annotations

import re
import unicodedata


def normalize_quote(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def quote_is_grounded(quote: str, source: str) -> bool:
    return normalize_quote(quote).casefold() in normalize_quote(source).casefold()


def abstention(reason: str) -> dict[str, object]:
    if reason not in {
        "NO_REVIEWS",
        "NO_CITABLE_SOURCE",
        "LEGACY_UNVERIFIED",
        "GROUNDING_FAILED",
    }:
        raise ValueError("unsupported abstention reason")
    return {
        "report_status": "abstained",
        "abstention_reason": reason,
        "claims": [],
        "key_complaints": [],
        "key_praises": [],
        "improvement_suggestions": [],
    }
