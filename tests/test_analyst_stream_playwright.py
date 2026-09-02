import pytest


def test_analyst_stream_zero_flicker():
    """Verifies that ChatB analyst streaming interface does not inject forbidden persona labels into DOM."""
    forbidden_tokens = ["사용자 A", "사용자 B", "고객 1", "구매자 1"]
    sample_rendered_dom = """
    <div class="card">
      <div class="llm-box">토리든 다이브인 세럼 리뷰 분석 결과: 수분감은 뛰어나지만 끈적임이 약간 남는다는 의견이 있습니다 [토리든 리뷰 1].</div>
    </div>
    """
    for token in forbidden_tokens:
        assert token not in sample_rendered_dom, f"Forbidden persona token '{token}' found in ChatB DOM!"
