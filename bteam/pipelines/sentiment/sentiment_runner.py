from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..model_adapters import TransformerSentimentAnalyzer

__all__ = [
    "SentimentResult",
    "TransformerSentimentAnalyzer",
    "classify",
    "classify_batch",
]


@dataclass(frozen=True)
class SentimentResult:
    sentence_id: int
    aspect: str
    label: str
    score: float


def classify(
    sentence_id: int, aspect: str, label: str, score: float
) -> SentimentResult:
    if not 0 <= score <= 1:
        raise ValueError("sentiment score must be between 0 and 1")
    return SentimentResult(sentence_id, aspect, label, score)


def classify_batch(
    rows: Iterable[tuple[int, str, str, float]],
) -> list[SentimentResult]:
    return [classify(*row) for row in rows]
