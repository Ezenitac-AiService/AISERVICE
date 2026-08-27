import pytest
from oliview_core.guardrails.pii_filter import mask_pii

from pipelines.sentence_split.split_runner import sanitize_pii


@pytest.mark.security
def test_pii_is_masked_before_vector_or_prompt_boundary():
    value = "연락처 test@example.com, 전화 010-1234-5678"
    masked = mask_pii(value)
    assert "test@example.com" not in masked
    assert "010-1234-5678" not in masked
    assert "[EMAIL]" in masked
    assert "[PHONE]" in masked


@pytest.mark.security
def test_account_and_resident_identifiers_are_masked_too():
    value = "계좌 110-123-456789, 주민번호 900101-1234567"
    masked = mask_pii(value)
    assert "110-123-456789" not in masked
    assert "900101-1234567" not in masked
    assert masked.count("[IDENTIFIER]") == 2
    assert sanitize_pii(value) == masked
