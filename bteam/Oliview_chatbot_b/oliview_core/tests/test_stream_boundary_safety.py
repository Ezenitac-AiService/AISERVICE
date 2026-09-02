import pytest


def test_streaming_token_interceptor_character_boundary_split_red_gate():
    """RED GATE: Asserts StreamingTokenInterceptor carry buffer holds back potential
    forbidden prefix '사용자 A' even when split across 1-character chunks."""
    try:
        from oliview_core.nodes.synthesis_node import StreamingTokenInterceptor  # type: ignore
        interceptor = StreamingTokenInterceptor(forbidden_patterns=["사용자 A", "사용자 B", "고객 1"])
        chunks = ["진정", " 효과는 ", "사", "용", "자", " ", "A", ": ", "정말 좋아요"]
        emitted = []
        for chunk in chunks:
            out = interceptor.process_chunk(chunk)
            if out:
                emitted.append(out)
        final = interceptor.finalize()
        if final:
            emitted.append(final)
        full_emitted = "".join(emitted)
        assert "사용자 A" not in full_emitted
        assert "진정 효과는" in full_emitted
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"RED GATE: StreamingTokenInterceptor not implemented: {exc}")
