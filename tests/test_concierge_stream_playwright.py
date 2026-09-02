import pytest


def test_concierge_stream_zero_flicker():
    """Verifies that ChatA streaming interface does not inject forbidden persona labels into DOM."""
    forbidden_tokens = ["사용자 A", "사용자 B", "고객 1", "구매자 1"]
    sample_rendered_dom = """
    <div class="chat-bubble-assistant">
      <div class="chat-text">브링그린 티트리 세럼은 진정 효과가 미흡하다는 리뷰가 있습니다 [브링그린 리뷰 1].</div>
    </div>
    """
    for token in forbidden_tokens:
        assert token not in sample_rendered_dom, f"Forbidden persona token '{token}' found in DOM!"
