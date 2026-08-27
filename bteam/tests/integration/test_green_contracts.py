from __future__ import annotations

import json
from pathlib import Path

import pytest
from oliview_core.cache.redis_manager import CacheVersionManager
from oliview_core.rag import RetrievalDocument, grounded_response

from pipelines.vector_indexer.indexer_runner import IncrementalIndexer, IndexDocument
from services.dashboard_backend.report_api import project_report

ROOT = Path(__file__).resolve().parents[2]


def test_zero_search_is_explicitly_abstained():
    result = grounded_response("없는 제품", [])
    assert result["status"] == "abstained"
    assert result["abstention_reason"] == "NO_CITABLE_SOURCE"
    assert result["citations"] == []


def test_rag_response_carries_source_review_citation():
    result = grounded_response(
        "커버력", [RetrievalDocument(7, 2, "커버력이 좋아요")], product_id=2
    )
    assert result["status"] == "grounded"
    assert result["citations"][0]["source_review_id"] == 7


def test_legacy_report_is_never_promoted_to_grounded():
    report = json.loads(
        (ROOT / "tests" / "fixtures" / "citation_fixture.json").read_text(
            encoding="utf-8"
        )
    )["grounded"]
    legacy = {
        key: value
        for key, value in report.items()
        if key
        not in {"claims", "key_complaints", "key_praises", "improvement_suggestions"}
    }
    projected = project_report(legacy)
    assert projected["report_status"] == "abstained"
    assert projected["abstention_reason"] == "LEGACY_UNVERIFIED"
    assert projected["claims"] == []


def test_vector_index_and_rag_cache_publish_only_after_upsert_success():
    calls = []
    cache = CacheVersionManager()
    indexer = IncrementalIndexer(lambda collection, metadata, ids: calls.append(ids))

    processed = indexer.index(
        [IndexDocument(42, 7, 2, "커버력이 좋아요")],
        product_id=2,
        cache_manager=cache,
    )

    assert processed == 1
    assert calls == [["42"]]
    assert cache.namespace(2, "rag") == "bteam:DEMO:product:2:rag:v2"


def test_cache_version_is_product_scoped_and_published_after_success():
    class RecordingPublisher:
        def __init__(self):
            self.events = []

        def publish(self, namespace, version):
            self.events.append((namespace, version))

    publisher = RecordingPublisher()
    cache = CacheVersionManager(publisher=publisher)

    first = cache.bump(2, "rag")
    second = cache.bump(7, "rag")

    assert first == "bteam:DEMO:product:2:rag:v2"
    assert second == "bteam:DEMO:product:7:rag:v2"
    assert cache.namespace(2, "rag").endswith(":v2")
    assert cache.namespace(7, "rag").endswith(":v2")
    assert publisher.events == [(first, 2), (second, 2)]


def test_cache_version_does_not_advance_when_durable_publish_fails():
    class FailingPublisher:
        def publish(self, namespace, version):
            raise OSError("redis unavailable")

    cache = CacheVersionManager(publisher=FailingPublisher())

    with pytest.raises(OSError, match="redis unavailable"):
        cache.bump(2, "rag")

    assert cache.namespace(2, "rag") == "bteam:DEMO:product:2:rag:v1"


def test_cache_version_continues_after_restart_from_durable_current_version():
    class PersistentPublisher:
        def __init__(self):
            self.current_value = 5
            self.events = []

        def current(self, namespace_prefix):
            return self.current_value

        def publish(self, namespace, version):
            self.current_value = version
            self.events.append((namespace, version))

    publisher = PersistentPublisher()
    cache = CacheVersionManager(publisher=publisher)

    namespace = cache.bump(14, "rag")

    assert namespace == "bteam:DEMO:product:14:rag:v6"
    assert publisher.events == [(namespace, 6)]
