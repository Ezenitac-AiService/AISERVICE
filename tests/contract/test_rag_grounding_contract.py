"""Real Oliview pipeline grounding and abstention contracts (T080)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

try:
    from bteam.Oliview_chatbot_a.oliview_core.grounding import assess_grounding, abstention_evidence
except (ImportError, ModuleNotFoundError):  # optional runtime wheels are unavailable on offline CI
    assess_grounding = None
    abstention_evidence = None


def _pipeline_or_skip():
    """Import the real pipeline only when optional runtime wheels are present."""

    try:
        from bteam.Oliview_chatbot_a.oliview_core import pipeline as pipeline_module
        from bteam.Oliview_chatbot_a.oliview_core.pipeline import OliviewPipeline
        from bteam.Oliview_chatbot_a.oliview_core.types import ReferenceReview
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"Oliview runtime dependencies unavailable: {exc}")
    return pipeline_module, OliviewPipeline, ReferenceReview


class _FakeRetriever:
    def __init__(self, results):
        self.results = results

    def search(self, **_kwargs):
        return list(self.results)


class _FakeReranker:
    def rerank(self, query, documents, top_k):
        del query, top_k
        return list(range(len(documents))), [0.95 - index * 0.1 for index in range(len(documents))], False


class _FakeClient:
    def __init__(self, output="근거 기반 답변 [1]"):
        self.settings = SimpleNamespace(synthesis_llm_model="test-llm")
        self.output = output
        self.invocations = 0

    def generate_stream(self, **_kwargs):
        self.invocations += 1
        return iter([self.output])


def test_zero_search_abstains_without_model_invocation() -> None:
    pipeline_module, OliviewPipeline, _ = _pipeline_or_skip()
    client = _FakeClient()
    pipeline = OliviewPipeline(client=client, retriever=_FakeRetriever([]), reranker=_FakeReranker())
    stream, metadata = pipeline.prepare_pipeline_stream("보습감이 어떤가요?")
    response = "".join(stream)
    assert metadata.selected_review_count == 0
    assert client.invocations == 0
    assert abstention_evidence is not None
    evidence = abstention_evidence()
    assert evidence["model_invoked"] is False
    assert evidence["citation_coverage_percent"] is None
    assert "근거" in response or "찾" in response
    del pipeline_module


def test_valid_evidence_uses_real_pipeline_and_full_citation_coverage(monkeypatch) -> None:
    pipeline_module, OliviewPipeline, ReferenceReview = _pipeline_or_skip()
    client = _FakeClient("수분감이 좋다는 리뷰가 있습니다. [1]")
    candidates = [{"review_id": 101, "clean_text": "촉촉하고 보습력이 좋아요.", "review_text": "촉촉하고 보습력이 좋아요."}]
    monkeypatch.setattr(pipeline_module, "fetch_review_metadata", lambda ids: {})
    pipeline = OliviewPipeline(client=client, retriever=_FakeRetriever(candidates), reranker=_FakeReranker())
    stream, metadata = pipeline.prepare_pipeline_stream("보습감이 어떤가요?")
    response = "".join(stream)
    assert metadata.selected_review_count == 1
    assert client.invocations == 1
    assert "[1]" in response
    reference = ReferenceReview(review_id=101, product_name="테스트 제품", clean_text="촉촉하고 보습력이 좋아요.")
    assert assess_grounding is not None
    evidence = assess_grounding(
        [{"claim_id": "claim-1"}],
        [{"claim_id": "claim-1", "document_id": "101", "result_index": 0, "quote": "보습력이 좋아요"}],
        [reference],
    )
    assert evidence["citation_coverage_percent"] == 100
    assert evidence["unsupported_claim_count"] == 0


def test_invalid_index_or_quote_is_not_clamped_or_accepted() -> None:
    if assess_grounding is None:
        pytest.skip("Oliview runtime dependencies unavailable")
    reference = SimpleNamespace(review_id=101, clean_text="촉촉하고 보습력이 좋아요.")
    evidence = assess_grounding(
        [{"claim_id": "claim-1"}],
        [{"claim_id": "claim-1", "document_id": "101", "result_index": 99, "quote": "없는 문장"}],
        [reference],
    )
    assert evidence["cited_claim_count"] == 0
    assert evidence["unsupported_claim_count"] == 1
    assert evidence["citation_coverage_percent"] == 0
    assert evidence["citations"] == []
