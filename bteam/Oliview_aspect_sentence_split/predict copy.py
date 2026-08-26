from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer


ROOT = Path(__file__).resolve().parent
MAX_LENGTH = 512
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# 토큰별 분류 번호: 속성 구간 밖(O), 시작(B), 내부(I)
OUTSIDE_TAG = 0
BEGIN_TAG = 1
INSIDE_TAG = 2


class AspectSentenceSplitter:
    """원본 리뷰에서 지정한 속성과 관련된 문장 구간 추출."""

    def __init__(
        self,
        model_dir: str | Path,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        # 잘못된 임곗값으로 모든 결과가 사라지거나 통과하는 문제 방지
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold는 0과 1 사이여야 합니다.")

        model_path = Path(model_dir)
        aspects_path = model_path / "aspects.json"
        if not aspects_path.is_file():
            raise FileNotFoundError(f"속성 목록 파일을 찾을 수 없습니다: {aspects_path}")

        # GPU 사용 가능하면 GPU, 아니면 CPU 사용
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)
        self.model = AutoModelForTokenClassification.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()

        self.confidence_threshold = confidence_threshold
        self.aspects = json.loads(aspects_path.read_text(encoding="utf-8"))
        self.aspect_set = set(self.aspects)

    def _select_aspects(
        self,
        aspect_mapping: dict[str, str] | None,
    ) -> dict[str, str]:
        # 매핑 형식: {DB에 저장할 속성명: 모델이 학습한 속성명}
        selected = (
            aspect_mapping
            if aspect_mapping is not None
            else {aspect: aspect for aspect in self.aspects}
        )
        unknown = sorted(set(selected.values()) - self.aspect_set)
        if unknown:
            raise ValueError(f"모델 aspects.json에 없는 속성입니다: {unknown}")
        return selected

    def _predict_tokens(
        self,
        model_aspect: str,
        review_text: str,
    ) -> tuple[list[int], list[list[int]], list[int | None], torch.Tensor]:
        # 찾을 속성과 원본 리뷰를 문장 쌍으로 토큰화
        encoded = self.tokenizer(
            model_aspect,
            review_text,
            truncation="only_second",
            max_length=MAX_LENGTH,
            return_offsets_mapping=True,
            return_tensors="pt",
        )

        # offset은 토큰을 원본 글자 위치로 되돌릴 때 사용
        offsets = encoded.pop("offset_mapping")[0].tolist()
        sequence_ids = encoded.sequence_ids(0)

        # KLUE-RoBERTa에서 사용하지 않는 문장 구분 번호 제거
        encoded.pop("token_type_ids", None)
        encoded = {name: value.to(self.device) for name, value in encoded.items()}

        # 각 토큰에 대해 O/B/I logits 계산 후 확률과 최종 태그 생성
        logits = self.model(**encoded).logits[0]
        probabilities = torch.softmax(logits, dim=-1)
        predictions = probabilities.argmax(dim=-1).tolist()
        return predictions, offsets, sequence_ids, probabilities

    def _decode_spans(
        self,
        review_text: str,
        output_aspect: str,
        model_aspect: str,
        predictions: list[int],
        offsets: list[list[int]],
        sequence_ids: list[int | None],
        probabilities: torch.Tensor,
    ) -> list[dict[str, str | int | float]]:
        # 연속된 B/I 토큰을 원본 리뷰의 하나의 문장 구간으로 복원
        results: list[dict[str, str | int | float]] = []
        span_start: int | None = None
        span_end: int | None = None
        span_scores: list[float] = []

        def save_current_span() -> None:
            nonlocal span_start, span_end, span_scores
            if span_start is None or span_end is None:
                return

            # 구간 시작과 끝에 포함된 공백 제거
            start, end = span_start, span_end
            while start < end and review_text[start].isspace():
                start += 1
            while end > start and review_text[end - 1].isspace():
                end -= 1

            phrase = review_text[start:end]
            confidence = sum(span_scores) / len(span_scores) if span_scores else 0.0
            if phrase and confidence >= self.confidence_threshold:
                results.append(
                    {
                        "aspect": output_aspect,
                        "model_aspect": model_aspect,
                        "aspect_phrase": phrase,
                        "start": start,
                        "end": end,
                        "confidence": round(confidence, 7),
                    }
                )

            span_start = None
            span_end = None
            span_scores = []

        for index, (tag, (start, end), sequence_id) in enumerate(
            zip(predictions, offsets, sequence_ids)
        ):
            # 첫 번째 문장인 속성명과 특수 토큰은 구간 복원에서 제외
            if sequence_id != 1:
                continue

            score = probabilities[index, tag].item()
            if tag == BEGIN_TAG:
                # 새 B가 나오면 이전 구간 저장 후 새 구간 시작
                save_current_span()
                span_start, span_end = start, end
                span_scores = [score]
            elif tag == INSIDE_TAG and span_start is not None:
                # B 뒤의 I는 현재 구간의 끝 위치 확장
                span_end = end
                span_scores.append(score)
            elif tag == OUTSIDE_TAG and span_start is not None:
                # O가 나오면 현재 구간 종료
                save_current_span()

        # 리뷰 마지막 토큰까지 구간이 이어진 경우 저장
        save_current_span()
        return results

    @torch.inference_mode()
    def extract(
        self,
        review_text: str,
        aspect_mapping: dict[str, str] | None = None,
    ) -> list[dict[str, str | int | float]]:
        # 외부에서 호출하는 문장 분리 함수
        review_text = str(review_text).strip()
        if not review_text:
            return []

        selected_aspects = self._select_aspects(aspect_mapping)
        results: list[dict[str, str | int | float]] = []

        # 속성 후보마다 같은 리뷰를 분석해 해당 속성 구간 추출
        for output_aspect, model_aspect in selected_aspects.items():
            predictions, offsets, sequence_ids, probabilities = self._predict_tokens(
                model_aspect,
                review_text,
            )
            results.extend(
                self._decode_spans(
                    review_text,
                    output_aspect,
                    model_aspect,
                    predictions,
                    offsets,
                    sequence_ids,
                    probabilities,
                )
            )

        return results


def parse_args() -> argparse.Namespace:
    # 터미널에서 모델 경로, 리뷰, 최소 신뢰도 입력
    parser = argparse.ArgumentParser(
        description="원본 리뷰에서 속성별 문장 구간을 추출합니다."
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=ROOT / "models" / "aspect_span_extractor",
    )
    parser.add_argument("--text", required=True, help="분석할 원본 리뷰")
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help="저장할 구간의 최소 평균 신뢰도(0~1)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    splitter = AspectSentenceSplitter(
        args.model_dir,
        confidence_threshold=args.confidence_threshold,
    )
    results = splitter.extract(args.text)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
