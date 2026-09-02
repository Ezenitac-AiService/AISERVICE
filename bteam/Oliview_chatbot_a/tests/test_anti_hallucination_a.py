import pytest
from pathlib import Path


def test_chata_anti_hallucination_fictional_users_red_gate():
    """RED GATE: Asserts ChatA groundedness sanitizer rejects fictional persona labels
    such as '사용자 A', '사용자 B', '고객 1'."""
    try:
        from oliview_core.guardrail import GroundednessSanitizer  # type: ignore
        sanitizer = GroundednessSanitizer()
        sample_dirty_output = '사용자 A: "진정 효과 정말 좋아요!" 사용자 B: "촉촉합니다."'
        result = sanitizer.sanitize_text(sample_dirty_output, valid_k=1, source_reviews=["진정 효과 좋은지 모르겠어요"])
        assert "사용자 A" not in result.sanitized_text
        assert "사용자 B" not in result.sanitized_text
        assert result.persona_removed_count > 0
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: GroundednessSanitizer not implemented for ChatA: {exc}")


def test_chata_exact_quote_replacement_red_gate():
    """RED GATE: Asserts ChatA converts mismatched direct quote into an objective summary."""
    try:
        from oliview_core.guardrail import GroundednessSanitizer  # type: ignore
        sanitizer = GroundednessSanitizer()
        fabricated_quote = '리뷰에서 "피부염이 다 나았어요"라고 하였습니다.'
        result = sanitizer.sanitize_text(fabricated_quote, valid_k=1, source_reviews=["진정 효과 좋은지 모르겠어요"])
        assert "피부염이 다 나았어요" not in result.sanitized_text
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: GroundednessSanitizer quote validation not implemented for ChatA: {exc}")
