from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer


ROOT = Path(__file__).resolve().parent
MAX_LENGTH = 512
DEFAULT_THRESHOLD = 0.5


class AspectSentenceSplitter:
    """원본 리뷰에서 속성별 문장 구간 추출."""

    def __init__(
        self,
        model_dir: str | Path,
        confidence_threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold는 0과 1 사이여야 합니다.")

        model_path = Path(model_dir)
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

    @torch.inference_mode()
    def extract(
        self,
        review_text: str,
        aspect_mapping: dict[str, str] | None = None,
    ) -> list[dict[str, str | int | float]]:
        review_text = str(review_text).strip()
        if not review_text:
            return []

        # {DB 표시명: 모델 학습 속성명}, 매핑이 없으면 전체 속성 분석
        selected_aspects = (
            aspect_mapping
            if aspect_mapping is not None
            else {aspect: aspect for aspect in self.aspects}
        )
        unknown = sorted(set(selected_aspects.values()) - set(self.aspects))
        if unknown:
            raise ValueError(f"모델에 없는 속성입니다: {unknown}")

        results: list[dict[str, str | int | float]] = []
        for output_aspect, model_aspect in selected_aspects.items():
            encoded = self.tokenizer(
                model_aspect,
                review_text,
                truncation="only_second",
                max_length=MAX_LENGTH,
                return_offsets_mapping=True,
                return_tensors="pt",
            )
            offsets = encoded.pop("offset_mapping")[0].tolist()
            sequence_ids = encoded.sequence_ids(0)
            encoded.pop("token_type_ids", None)
            encoded = {name: value.to(self.device) for name, value in encoded.items()}

            # 리뷰의 각 토큰을 O(0), B(1), I(2) 중 하나로 분류
            logits = self.model(**encoded).logits[0]
            probabilities = torch.softmax(logits, dim=-1)
            predictions = probabilities.argmax(dim=-1).tolist()

            start = end = None
            scores: list[float] = []

            def save_span() -> None:
                nonlocal start, end, scores
                if start is None or end is None:
                    return

                phrase_start, phrase_end = start, end
                while phrase_start < phrase_end and review_text[phrase_start].isspace():
                    phrase_start += 1
                while phrase_end > phrase_start and review_text[phrase_end - 1].isspace():
                    phrase_end -= 1

                phrase = review_text[phrase_start:phrase_end]
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

                if tag == 1:  # B: 새 구간 시작
                    save_span()
                    start, end, scores = token_start, token_end, [score]
                elif tag == 2 and start is not None:  # I: 현재 구간 연장
                    end = token_end
                    scores.append(score)
                elif tag == 0 and start is not None:  # O: 현재 구간 종료
                    save_span()

            save_span()

        return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="원본 리뷰에서 속성별 문장 구간 추출"
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=ROOT / "models" / "aspect_span_extractor",
    )
    parser.add_argument("--text", required=True)
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
    )
    args = parser.parse_args()

    splitter = AspectSentenceSplitter(
        args.model_dir,
        confidence_threshold=args.confidence_threshold,
    )
    print(json.dumps(splitter.extract(args.text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
