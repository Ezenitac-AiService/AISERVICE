import pytest


def test_exact_quote_matching_nfc_and_crlf_red_gate():
    """RED GATE: Asserts exact-match quote verification strictly preserves punctuation
    and only normalizes NFC and newlines (CRLF/CR -> LF)."""
    try:
        from oliview_core.guardrail import verify_exact_quote_match  # type: ignore
        source = "진정 효과 좋은지 모르겠어요.\r\n피부 자극은 없었습니다."
        exact_candidate = "진정 효과 좋은지 모르겠어요.\n피부 자극은 없었습니다."
        assert verify_exact_quote_match(exact_candidate, source) is True

        # Fails if whitespace/punctuation was modified
        tampered_candidate = "진정효과 좋은지 모르겠어요. 피부 자극은 없었습니다."
        assert verify_exact_quote_match(tampered_candidate, source) is False
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: verify_exact_quote_match not implemented in oliview_core.guardrail: {exc}")


def test_pii_quote_redaction_and_display_quote_red_gate():
    """RED GATE: Asserts PII-bearing quote matches server source internally
    but emits redacted display_quote with quote_redacted=True."""
    try:
        from oliview_core.guardrail import sanitize_citation_quote  # type: ignore
        source = "제 전화번호는 010-1234-5678입니다. 보습력 좋습니다."
        candidate = "제 전화번호는 010-1234-5678입니다. 보습력 좋습니다."
        citation_view = sanitize_citation_quote(candidate, source, review_index=1, review_id="rev_01")
        assert citation_view.quote_redacted is True
        assert "010-1234-5678" not in citation_view.display_quote
        assert "[전화번호]" in citation_view.display_quote
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: sanitize_citation_quote not implemented in oliview_core.guardrail: {exc}")
