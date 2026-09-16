"""
Integration test for ChatB dynamic 15-review RAG ingestion and zero prompt truncation (T030 / US3 / FR-009).
Validates:
- 15 review documents (each >200 chars) are fully preserved in RAG context
- Legacy 1,500-char clamp and 150-char sentence truncation are eradicated
- qwen3.5-9b 32K context profile supports full 1~15 review ingestion without data loss
"""

import pytest
from Oliview_chatbot_b.common import budget_context_documents, RecommendedProduct


def test_chatb_15reviews_rag_no_truncation():
    """US3: 15 full reviews must be budgeted without 1500-char clamp or 150-char sentence truncation."""
    # Create 15 sample review items each with ~300 character sentences
    reviews = []
    for i in range(15):
        long_sentence = (
            f"리뷰 {i+1}번: 이 제품은 보습력이 뛰어나고 민감한 피부에도 자극이 전혀 없으며, "
            f"끈적임 없이 빠르게 흡수되어 하루 종일 촉촉함을 유지해 줍니다. "
            f"향도 은은한 천연 아로마 향이라 부담 없이 사용할 수 있어서 지인들에게도 적극 추천하고 싶습니다. "
            f"재구매 의사 100%이며 건조한 환절기에 필수 아이템입니다. 별점 5점 만점에 5점 드립니다!"
        )
        assert len(long_sentence) > 150, "Test fixture sentence must be >150 chars to test truncation eradication"
        
        prod = RecommendedProduct(
            rank=i + 1,
            product_name=f"올리브영 베스트 수분크림 {i+1}호",
            brand_name="올리브뷰티",
            category="스킨케어",
            separated_sentence=long_sentence,
            display_name=f"크림 {i+1}",
            sentiment_label="긍정",
            cosine_similarity=0.95 - (i * 0.01),
            rerank_score=0.98 - (i * 0.01)
        )
        reviews.append(prod)

    # Budget documents for 9B synthesis model
    budgeted = budget_context_documents(reviews, model_name="qwen3.5-9b", is_9b=True)

    # Must preserve all 15 reviews
    assert len(budgeted) == 15, f"Expected all 15 reviews to be preserved, got {len(budgeted)}"

    # Must NOT truncate sentence with "..."
    for idx, item in enumerate(budgeted):
        assert not item.separated_sentence.endswith("..."), (
            f"Review {idx+1} sentence was truncated with '...': {item.separated_sentence}"
        )
        assert len(item.separated_sentence) > 150, (
            f"Review {idx+1} sentence length was clamped below 150 chars: {len(item.separated_sentence)}"
        )


def test_chatb_dict_reviews_15_ingestion():
    """US3: 15 dictionary reviews must also be preserved without 1500-char clamp."""
    dict_reviews = [
        {
            "rank": i + 1,
            "product_name": f"세럼 {i+1}",
            "brand_name": "브랜드A",
            "category": "에센스",
            "separated_sentence": f"이 세럼은 고농축 펩타이드 성분이 함유되어 탄력 개선에 매우 탁월하며 끈적임이 없습니다. " * 3,
            "display_name": f"세럼 {i+1}",
            "sentiment_label": "긍정",
            "cosine_similarity": 0.9,
            "rerank_score": 0.95
        }
        for i in range(15)
    ]

    budgeted = budget_context_documents(dict_reviews, model_name="qwen3.5-9b", is_9b=True)
    assert len(budgeted) == 15
    for item in budgeted:
        assert not item["separated_sentence"].endswith("...")
