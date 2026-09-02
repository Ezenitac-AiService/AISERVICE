import sys
from pathlib import Path
import pytest

CHATB_DIR = Path(__file__).resolve().parents[1]
if str(CHATB_DIR) not in sys.path:
    sys.path.insert(0, str(CHATB_DIR))


def test_chatb_anti_hallucination_fictional_users_red_gate():
    """RED GATE: Asserts ChatB groundedness sanitizer rejects fictional persona labels
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
        pytest.fail(f"RED GATE: GroundednessSanitizer not implemented for ChatB: {exc}")


def test_chatb_legacy_it_prompt_absence_red_gate():
    """RED GATE: Asserts that ChatB does not contain or reference NO_THINK_SYSTEM_PROMPT or IT assistant prompt."""
    import common  # type: ignore
    assert not hasattr(common, "NO_THINK_SYSTEM_PROMPT"), "RED GATE: common.py still has NO_THINK_SYSTEM_PROMPT"
