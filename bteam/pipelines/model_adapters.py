"""Lazy adapters for the preserved local sentence and sentiment models.

The pipeline image can start and run stages that do not need these models.  A
model-backed stage imports torch/transformers only when it has eligible input;
missing runtime dependencies then fail the stage closed instead of recording a
false checkpoint.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from urllib.request import Request, urlopen

from oliview_core.gateway.client import GatewayClient
from oliview_core.guardrails.pii_filter import mask_pii


class TransformerSentenceSplitter:
    def __init__(self, model_dir: str | Path, confidence_threshold: float = 0.7):
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        try:
            import torch  # type: ignore[import-not-found]
            from transformers import (  # type: ignore[import-not-found]
                AutoModelForTokenClassification,
                AutoTokenizer,
            )
        except ImportError as error:  # pragma: no cover - depends on image extras
            raise RuntimeError("torch and transformers are required for sentence_split") from error

        model_path = Path(model_dir)
        self._torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)
        self.model = AutoModelForTokenClassification.from_pretrained(model_path).to(
            self.device
        )
        self.model.eval()
        self.confidence_threshold = confidence_threshold
        self.aspects = json.loads(
            (model_path / "aspects.json").read_text(encoding="utf-8")
        )

    def extract(
        self, review_text: str, aspect_mapping: dict[str, str]
    ) -> list[dict[str, str | int | float]]:
        torch = self._torch
        text = str(review_text).strip()
        if not text:
            return []
        unknown = sorted(set(aspect_mapping.values()) - set(self.aspects))
        if unknown:
            raise ValueError(f"model attributes are not available: {unknown}")

        results: list[dict[str, str | int | float]] = []
        for output_aspect, model_aspect in aspect_mapping.items():
            encoded = self.tokenizer(
                model_aspect,
                text,
                truncation="only_second",
                max_length=512,
                return_offsets_mapping=True,
                return_tensors="pt",
            )
            offsets = encoded.pop("offset_mapping")[0].tolist()
            sequence_ids = encoded.sequence_ids(0)
            encoded.pop("token_type_ids", None)
            encoded = {name: value.to(self.device) for name, value in encoded.items()}
            with torch.inference_mode():
                probabilities = torch.softmax(self.model(**encoded).logits[0], dim=-1)
            predictions = probabilities.argmax(dim=-1).tolist()
            start: int | None = None
            end: int | None = None
            scores: list[float] = []

            def save_span(
                output_aspect: str = output_aspect,
                model_aspect: str = model_aspect,
            ) -> None:
                nonlocal start, end, scores
                if start is None or end is None or not scores:
                    return
                phrase_start = start
                phrase_end = end
                while phrase_start < phrase_end and text[phrase_start].isspace():
                    phrase_start += 1
                while phrase_end > phrase_start and text[phrase_end - 1].isspace():
                    phrase_end -= 1
                phrase = text[phrase_start:phrase_end]
                confidence = sum(scores) / len(scores)
                if phrase and confidence >= self.confidence_threshold:
                    results.append(
                        {
                            "aspect": output_aspect,
                            "model_aspect": model_aspect,
                            "aspect_phrase": phrase,
                            "start": phrase_start,
                            "end": phrase_end,
                            "confidence": round(confidence, 7),
                        }
                    )
                start = end = None
                scores = []

            for index, (tag, offset, sequence_id) in enumerate(
                zip(predictions, offsets, sequence_ids)
            ):
                if sequence_id != 1:
                    continue
                token_start, token_end = offset
                score = probabilities[index, tag].item()
                if tag == 1:
                    save_span()
                    start, end, scores = token_start, token_end, [score]
                elif tag == 2 and start is not None:
                    end = token_end
                    scores.append(score)
                elif tag == 0 and start is not None:
                    save_span()
            save_span()
        return results


class TransformerSentimentAnalyzer:
    def __init__(self, model_dir: str | Path):
        try:
            import torch  # type: ignore[import-not-found]
            from transformers import (  # type: ignore[import-not-found]
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as error:  # pragma: no cover - depends on image extras
            raise RuntimeError("torch and transformers are required for sentiment") from error
        self._torch = torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(
            self.device
        )
        self.model.eval()

    def predict_many(self, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        if not rows:
            return []
        torch = self._torch
        inputs = [
            f"[속성] {row.get('model_attribute_name', '')} "
            f"[문장] {row.get('separated_sentence', '')}"
            for row in rows
        ]
        encoded = self.tokenizer(
            inputs,
            return_tensors="pt",
            truncation=True,
            max_length=64,
            padding=True,
        )
        encoded = {name: value.to(self.device) for name, value in encoded.items()}
        with torch.inference_mode():
            probabilities = torch.softmax(self.model(**encoded).logits, dim=-1)
        predicted_ids = probabilities.argmax(dim=-1)
        return [
            {
                "aspect_sentence_id": row["aspect_sentence_id"],
                "sentiment_label": self.model.config.id2label[int(predicted_id)],
                "confidence_score": round(
                    float(row_probabilities[int(predicted_id)]), 7
                ),
            }
            for row, row_probabilities, predicted_id in zip(
                rows, probabilities, predicted_ids
            )
        ]


class GatewayReportGenerator:
    """OpenAI-compatible model Gateway adapter for structured reports."""

    def __init__(self, endpoints: list[Mapping[str, object]], model: str):
        if not endpoints:
            raise ValueError("at least one report Gateway endpoint is required")
        self.client = GatewayClient(
            [dict(endpoint) for endpoint in endpoints]
        )
        self.model = model

    def generate(self, product_id: int, rows: list[dict[str, object]]) -> dict[str, object]:
        safe_rows = [
            {
                "source_review_id": int(str(row["review_id"])),
                "aspect_sentence_id": int(str(row["aspect_sentence_id"])),
                "analysis_category_id": int(str(row["analysis_category_id"])),
                "display_name": str(row.get("display_name") or ""),
                "sentiment_label": str(row.get("sentiment_label") or ""),
                "quote": mask_pii(str(row.get("separated_sentence") or "")),
            }
            for row in rows
        ]
        prompt = (
            "Generate a JSON product review report only. Every claim must cite one "
            "source_review_id from the supplied rows and use an exact safe quote. "
            "Return keys overall_summary, attributes, claims, "
            "improvement_suggestions. Each claim has claim_key, claim_kind, "
            "claim_text, citations; each citation has source_review_id and quote. "
            f"product_id={product_id}; rows={json.dumps(safe_rows, ensure_ascii=False)}"
        )

        def call(endpoint: str) -> object:
            body = json.dumps(
                {
                    "model": self.model,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            request = Request(
                f"{endpoint.rstrip('/')}/v1/chat/completions",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))

        response = self.client.call(call).value
        if not isinstance(response, Mapping):
            raise TypeError("model Gateway response must be an object")
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("model Gateway response has no choices")
        first = choices[0]
        content: object = first
        if isinstance(first, Mapping):
            message = first.get("message")
            content = message.get("content") if isinstance(message, Mapping) else first.get("text")
        if not isinstance(content, str):
            raise TypeError("model Gateway response content must be text")
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.strip("`").removeprefix("json").strip()
        parsed = json.loads(normalized)
        if not isinstance(parsed, dict):
            raise TypeError("model Gateway report must be a JSON object")
        return dict(parsed)
