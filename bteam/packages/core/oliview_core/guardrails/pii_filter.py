from __future__ import annotations

import re

PATTERNS = (
    (re.compile(r"(?<!\d)\d{6}-\d{7}(?!\d)"), "[IDENTIFIER]"),
    (re.compile(r"(?<!\d)\d{3}-\d{2,3}-\d{4,6}(?!\d)"), "[IDENTIFIER]"),
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (
        re.compile(r"(?<!\d)(?:\+?82[- .]?)?0?1\d[- .]?\d{3,4}[- .]?\d{4}(?!\d)"),
        "[PHONE]",
    ),
)


def mask_pii(text: str) -> str:
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text
