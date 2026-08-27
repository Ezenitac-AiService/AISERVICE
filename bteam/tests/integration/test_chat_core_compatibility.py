from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from oliview_core.chat import ChatEngine
from oliview_core.rag import RetrievalDocument

from oliview_core.retrieval import hybrid_retrieve
from oliview_core.session import InMemorySessionStore
from services.chatbot_a.app import Handler as ChatAHandler
from services.chatbot_b.main import Handler as ChatBHandler


def test_hybrid_retrieval_combines_lexical_and_vector_results_with_product_scope():
    lexical = [
        RetrievalDocument(1, 7, "촉촉하고 발림성이 좋아요"),
        RetrievalDocument(2, 7, "보습감은 무난하지만 향이 강해요"),
        RetrievalDocument(3, 8, "촉촉한 다른 제품 후기"),
    ]
    vector_rows = [
        {
            "source_review_id": 2,
            "product_id": 7,
            "text": "보습감은 무난하지만 향이 강해요",
        },
        {"source_review_id": 3, "product_id": 8, "text": "촉촉한 다른 제품 후기"},
    ]

    results = hybrid_retrieve(
        "촉촉한 보습감",
        lexical,
        vector_rows,
        product_id=7,
        limit=5,
    )

    assert {row["source_review_id"] for row in results} == {1, 2}
    assert results[0]["source_review_id"] == 2
    assert all(row["product_id"] == 7 for row in results)
    assert all(float(row["rerank_score"]) >= 0 for row in results)


def test_chat_engine_preserves_session_and_emits_grounded_sse_events():
    store = InMemorySessionStore()
    engine = ChatEngine(session_store=store)
    payload = {
        "query": "이 제품은 촉촉한가요?",
        "session_id": "compat-session",
        "product_id": 7,
        "documents": [
            {
                "source_review_id": 11,
                "product_id": 7,
                "text": "촉촉하고 발림성이 좋아요. 연락처 010-1234-5678",
            },
            {
                "source_review_id": 12,
                "product_id": 8,
                "text": "다른 상품 후기",
            },
        ],
    }

    events = list(engine.stream(payload, service="chatbot_a", trace_id="trace-1"))
    event_types = [str(event["event_type"]) for event in events]
    step_ids = [
        str(event.get("step_id"))
        for event in events
        if event["event_type"] == "step_update"
    ]
    complete = next(event for event in events if event["event_type"] == "complete")

    assert event_types[0] == "step_update"
    assert "token" in event_types
    assert event_types[-1] == "complete"
    assert step_ids == [
        "INTENT_ANALYSIS",
        "HYBRID_SEARCH",
        "RERANKING",
        "LLM_SYNTHESIS",
    ]
    assert complete["status"] == "grounded"
    assert complete["citations"] == [
        {"source_review_id": 11, "quote": "촉촉하고 발림성이 좋아요. 연락처 [PHONE]"}
    ]
    assert store.get_messages("compat-session")[0]["role"] == "user"
    assert "010-1234-5678" not in json.dumps(
        store.get_messages("compat-session"), ensure_ascii=False
    )


def test_chat_engine_abstains_without_citable_source_and_supports_session_clear():
    store = InMemorySessionStore()
    engine = ChatEngine(session_store=store)
    response = engine.respond(
        {"query": "근거 없는 질문", "session_id": "empty-session"},
        service="chatbot_b",
    )

    assert response["status"] == "abstained"
    assert response["abstention_reason"] == "NO_CITABLE_SOURCE"
    assert response["citations"] == []
    assert store.get_messages("empty-session")
    store.clear_session("empty-session")
    assert store.get_messages("empty-session") == []


def test_chat_engine_rejects_nonexistent_or_cross_product_citations():
    store = InMemorySessionStore()
    lookup = lambda _ids: {
        31: {"product_id": 7, "review_content": "촉촉하고 순해요"}
    }
    engine = ChatEngine(session_store=store, review_lookup=lookup)

    grounded = engine.respond(
        {
            "query": "촉촉한가요?",
            "product_id": 7,
            "documents": [
                {"source_review_id": 31, "product_id": 7, "text": "촉촉하고 순해요"}
            ],
        },
        service="chatbot_a",
    )
    rejected = engine.respond(
        {
            "query": "검증되지 않은 문장인가요?",
            "product_id": 7,
            "documents": [
                {"source_review_id": 99, "product_id": 7, "text": "검증되지 않은 문장"}
            ],
        },
        service="chatbot_a",
    )

    assert grounded["status"] == "grounded"
    assert rejected["status"] == "abstained"
    assert rejected["abstention_reason"] == "GROUNDING_FAILED"


def test_chat_a_and_chat_b_expose_legacy_sync_stream_and_session_routes():
    request_payload = {
        "query": "촉촉함을 알려줘",
        "session_id": "http-compat-session",
        "product_id": 7,
        "documents": [
            {"source_review_id": 21, "product_id": 7, "text": "촉촉하고 순해요"}
        ],
    }
    for handler, stream_path in (
        (ChatAHandler, "/bteam/chata/api/v1/chat/stream"),
        (ChatBHandler, "/bteam/chatb/api/v1/search/stream"),
    ):
        handler.chat_engine = ChatEngine(session_store=InMemorySessionStore())
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            encoded = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
            connection.request(
                "POST",
                "/api/v1/chat",
                body=encoded,
                headers={"Content-Type": "application/json"},
            )
            sync_response = connection.getresponse()
            sync_payload = json.loads(sync_response.read())
            connection.close()
            assert sync_response.status == 200
            assert sync_payload["status"] == "grounded"
            assert sync_payload["citations"][0]["source_review_id"] == 21

            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request(
                "POST",
                stream_path,
                body=encoded,
                headers={"Content-Type": "application/json"},
            )
            stream_response = connection.getresponse()
            stream_body = stream_response.read().decode("utf-8")
            connection.close()
            assert stream_response.status == 200
            assert "event: step_update" in stream_body
            assert "event: token" in stream_body
            assert "event: complete" in stream_body

            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("GET", "/api/session/http-compat-session/history")
            history_response = connection.getresponse()
            history_payload = json.loads(history_response.read())
            connection.close()
            assert history_response.status == 200
            assert history_payload["count"] >= 2

            connection = HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("DELETE", "/api/session/http-compat-session")
            clear_response = connection.getresponse()
            connection.close()
            assert clear_response.status == 200
        finally:
            server.shutdown()
            thread.join()
