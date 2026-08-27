from __future__ import annotations

import re
from collections.abc import Iterable

from oliview_core.guardrails.pii_filter import mask_pii

# The production adapter is lazy: torch/transformers are imported only when a
# stage actually has eligible reviews. Keep the public module boundary named
# by the pipeline plan while retaining one implementation of the model logic.
from ..model_adapters import TransformerSentenceSplitter

__all__ = [
    "TransformerSentenceSplitter",
    "process_reviews",
    "sanitize_pii",
    "split_sentences",
]


def sanitize_pii(text: str) -> str:
    return mask_pii(text)


def split_sentences(text: str) -> list[str]:
    clean = sanitize_pii(text)
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", clean)
        if sentence.strip()
    ]


def process_reviews(reviews: Iterable[str]) -> list[str]:
    sentences: list[str] = []
    for review in reviews:
        sentences.extend(split_sentences(review))
    return sentences
