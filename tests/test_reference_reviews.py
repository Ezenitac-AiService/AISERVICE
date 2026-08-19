# tests/test_reference_reviews.py
"""
올리챗 A/B 공통 참조 리뷰 구조화 및 순위 메타데이터 검증 테스트 (US2)
"""

import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "bteam" / "Oliview_chatbot_a"))

from common.step_callback import (
    PipelinePhase,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
)


def test_reference_reviews_data_integrity():
    """참조 리뷰 객체의 랭크, 속성, 감성 라벨 및 리랭커 점수 무결성 검증"""
    reviews = [
        ReferenceReview(
            rank=1,
            product_name="헤라 블랙 쿠션",
            brand_name="헤라",
            category="베이스메이크업",
            review_score=5,
            attribute_tag="밀착력",
            sentiment_label="긍정",
            separated_sentence="밀착력이 아주 우수하고 하루 종일 무너짐이 없습니다.",
            rerank_score=0.9654,
        ),
        ReferenceReview(
            rank=2,
            product_name="헤라 블랙 쿠션",
            brand_name="헤라",
            category="베이스메이크업",
            review_score=4,
            attribute_tag="커버력",
            sentiment_label="긍정",
            separated_sentence="홍조와 옅은 잡티는 가볍게 커버됩니다.",
            rerank_score=0.8912,
        ),
    ]

    metadata = RagExecutionMetadata(
        total_latency_sec=1.12,
        searched_review_count=20,
        selected_review_count=len(reviews),
        model_used="qwen3.5-4b",
        fallback_triggered=False,
        reference_reviews=reviews,
    )

    assert metadata.selected_review_count == 2
    assert metadata.reference_reviews[0].rank == 1
    assert metadata.reference_reviews[0].attribute_tag == "밀착력"
    assert metadata.reference_reviews[1].rerank_score < metadata.reference_reviews[0].rerank_score


def test_reference_review_score_formatting():
    """리랭크 스코어 및 텍스트 슬라이싱 포맷팅 검증"""
    ref = ReferenceReview(
        rank=1,
        product_name="식물나라 선크림",
        brand_name="식물나라",
        category="선케어",
        review_score=5,
        attribute_tag="지속력",
        sentiment_label="긍정",
        separated_sentence="야외 활동 시 땀을 흘려도 지속력이 오래 유지됩니다.",
        rerank_score=0.923456,
    )

    formatted_score = f"{ref.rerank_score:.4f}"
    assert formatted_score == "0.9235"
    assert len(ref.separated_sentence) > 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    test_reference_reviews_data_integrity()
    test_reference_review_score_formatting()
    print("[SUCCESS] test_reference_reviews.py: All tests passed successfully!")
