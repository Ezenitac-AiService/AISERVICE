"""Unit tests for cosmetic negative aspect lexicon and polarity guardrails (Spec 038 US2)."""
import pytest
from oliview_core.models.aspect_lexicon import (
    is_negative_aspect,
    get_aspect_guard_instruction,
    NEGATIVE_ASPECT_LEXICON,
    NEGATIVE_ASPECT_TERMS,
    AspectPolarity,
)
from oliview_core.guardrail import sanitize_negative_aspect_distortions


def test_negative_aspect_lexicon_terms():
    """모든 뷰티 부정 속성어가 NEGATIVE 극성으로 올바르게 매핑되어 있는지 검증."""
    assert is_negative_aspect("각질부각") is True
    assert is_negative_aspect("요철부각") is True
    assert is_negative_aspect("들뜸") is True
    assert is_negative_aspect("밀림") is True
    assert is_negative_aspect("다크닝") is True
    assert is_negative_aspect("뭉침") is True
    assert is_negative_aspect("가루날림") is True
    assert is_negative_aspect("건조함") is True
    assert is_negative_aspect("번짐") is True

    # 긍정/중립 속성은 False
    assert is_negative_aspect("촉촉함") is False
    assert is_negative_aspect("발림성") is False
    assert is_negative_aspect("지속력") is False


def test_aspect_guard_instruction_injection():
    """부정 속성어 질의 시 시스템 프롬프트용 가이드라인이 올바르게 생성되는지 검증."""
    aspects = ["촉촉함", "각질부각", "요철부각"]
    instruction = get_aspect_guard_instruction(aspects)

    assert "각질부각" in instruction
    assert "요철부각" in instruction
    assert "각질이 부각되는지(도드라지는지) 여부" in instruction
    assert "절대로 '각질부각 효과가 좋다/개선된다'와 같이 긍정 장점으로 왜곡하지 말고" in instruction


def test_sanitize_negative_aspect_distortions_corrector():
    """LLM이 부정 속성을 '각질부각 효과'와 같이 왜곡했을 때 후처리 가드레일이 정정하는지 검증."""
    distorted_text = (
        "1. 만족스러운 점:\n"
        "- 각질부각 효과: 거친 각질을 부드럽게 해주는 데 도움이 됩니다 [리뷰 1].\n"
        "- 보습력: 매우 촉촉합니다 [리뷰 2]."
    )

    corrected = sanitize_negative_aspect_distortions(distorted_text)

    assert "각질부각 효과" not in corrected
    assert "각질 부각 여부" in corrected or "각질 케어/부각 완화" in corrected
