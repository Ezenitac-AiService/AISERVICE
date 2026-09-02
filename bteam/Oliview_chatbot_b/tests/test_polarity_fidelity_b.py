import sys
from pathlib import Path
import pytest

CHATB_DIR = Path(__file__).resolve().parents[1]
if str(CHATB_DIR) not in sys.path:
    sys.path.insert(0, str(CHATB_DIR))


def test_chatb_polarity_fidelity_preserves_negative_feedback_red_gate():
    """RED GATE: Asserts ChatB synthesis preserves negative and doubtful feedback
    without inverting polarity into false positive claims."""
    try:
        from oliview_core.guardrail import GroundednessSanitizer  # type: ignore
        sanitizer = GroundednessSanitizer()
        inverted_output = "1. 진정 효과에 대한 긍정적 평가: 피부가 안정적입니다 [브링그린 리뷰 1]."
        source_review = "진정 효과 좋은지 모르겠어요"
        result = sanitizer.sanitize_text(inverted_output, valid_k=1, source_reviews=[source_review])
        assert not result.is_grounded or "긍정적 평가" not in result.sanitized_text
        assert "체감이 부족" in result.sanitized_text or result.claims_removed_count > 0
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: GroundednessSanitizer polarity verification not implemented for ChatB: {exc}")
