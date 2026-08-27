import json
from datetime import UTC, datetime
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from oliview_core.db.orm import (
    AnalysisCategoryAttribute,
    Base,
    Product,
    ProductReport,
    ProductReportAttribute,
    ProductReportCitationORM,
    ProductReportClaimORM,
    Review,
    ReviewSentence,
    SentimentAnalysis,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from services.dashboard_backend import app as dashboard_app
from services.dashboard_backend.app import Handler
from services.dashboard_backend.report_api import load_report_db


class FakeDashboardSearch:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def respond(self, payload: dict[str, object], *, service: str) -> dict[str, object]:
        self.payloads.append(payload)
        return {
            "status": "grounded",
            "service": service,
            "citations": [{"source_review_id": 41, "quote": "향이 좋아요"}],
        }


def test_dashboard_loads_grounded_report_from_normalized_tables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(
                product_id=2,
                product_code="p2",
                product_name="Test product",
            )
        )
        session.add(
            Review(
                review_id=7,
                review_code=700,
                product_id=2,
                review_content="커버력이 좋아요",
            )
        )
        report = ProductReport(
            llm_product_report_id=1,
            product_id=2,
            report_status="grounded",
            generated_at=datetime.now(UTC),
        )
        session.add(report)
        session.flush()
        claim = ProductReportClaimORM(
            llm_product_report_id=report.llm_product_report_id,
            claim_key="coverage",
            claim_kind="praise",
            claim_text="커버력이 좋다는 평가가 있습니다.",
        )
        session.add(claim)
        session.flush()
        session.add(
            ProductReportCitationORM(
                report_claim_id=claim.report_claim_id,
                source_review_id=7,
                quote_text="커버력이 좋아요",
            )
        )
        session.commit()

        result = load_report_db(session, 1)

    assert result is not None
    assert result["report_status"] == "grounded"
    assert result["claims"][0]["citations"][0]["source_review_id"] == 7


def test_dashboard_projects_legacy_db_report_as_abstained():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(
                product_id=2,
                product_code="p2",
                product_name="Legacy product",
            )
        )
        session.add(
            ProductReport(
                llm_product_report_id=2,
                product_id=2,
                report_status="abstained",
                generated_at=datetime.now(UTC),
            )
        )
        session.commit()
        result = load_report_db(session, 2)

    assert result is not None
    assert result["report_status"] == "abstained"
    assert result["abstention_reason"] == "LEGACY_UNVERIFIED"


def test_dashboard_returns_attribute_rows_and_product_sentiment_statistics():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(
                product_id=3,
                product_code="p3",
                product_name="Stats product",
            )
        )
        session.add_all(
            [
                Review(
                    review_id=31,
                    review_code=310,
                    product_id=3,
                    review_content="발림성이 좋아요",
                ),
                ReviewSentence(
                    aspect_sentence_id=301,
                    review_id=31,
                    analysis_category_id=1,
                    model_attribute_name="spread",
                    separated_sentence="발림성이 좋아요",
                ),
                AnalysisCategoryAttribute(
                    analysis_category_id=1,
                    model_attribute_name="spread",
                    display_name="발림성",
                    display_order=1,
                ),
                SentimentAnalysis(
                    aspect_sentence_id=301,
                    sentiment_label="긍정",
                    confidence_score=0.99,
                ),
                ProductReport(
                    llm_product_report_id=3,
                    product_id=3,
                    report_status="abstained",
                    generated_at=datetime.now(UTC),
                ),
                ProductReportAttribute(
                    llm_product_attribute_report_id=301,
                    llm_product_report_id=3,
                    product_id=3,
                    analysis_category_id=1,
                    display_name="발림성",
                    positive_summary="부드럽게 발린다는 평가",
                    negative_summary="",
                    generated_at=datetime.now(UTC),
                ),
            ]
        )
        session.commit()

        result = load_report_db(session, 3)

    assert result is not None
    assert result["product_code"] == "p3"
    assert result["total_reviews_analyzed"] == 1
    assert result["attributes"][0]["display_name"] == "발림성"
    assert result["attributes"][0]["positive_summary"] == "부드럽게 발린다는 평가"
    assert result["aspect_summary"]["발림성"] == {
        "positive_count": 1,
        "negative_count": 0,
        "neutral_count": 0,
        "positive_ratio": 100.0,
    }
    assert result["statistics"]["total_sentence_count"] == 1


def test_dashboard_http_returns_grounded_schema_v2_with_same_product_citation():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Product(
                    product_id=4,
                    product_code="p4",
                    product_name="HTTP product",
                ),
                Review(
                    review_id=41,
                    review_code=410,
                    product_id=4,
                    review_content="향이 좋아요",
                ),
                ProductReport(
                    llm_product_report_id=4,
                    product_id=4,
                    report_status="grounded",
                    overall_summary="향에 대한 평가입니다.",
                    generated_at=datetime.now(UTC),
                ),
            ]
        )
        session.flush()
        claim = ProductReportClaimORM(
            llm_product_report_id=4,
            claim_key="scent",
            claim_kind="praise",
            claim_text="향이 좋다는 평가가 있습니다.",
        )
        session.add(claim)
        session.flush()
        session.add(
            ProductReportCitationORM(
                report_claim_id=claim.report_claim_id,
                source_review_id=41,
                quote_text="향이 좋아요",
            )
        )
        session.commit()

    previous_engine = dashboard_app._DATABASE_ENGINE
    dashboard_app._DATABASE_ENGINE = engine
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1])
        connection.request("GET", "/bteam/oliview/api/reports/4")
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
    finally:
        server.shutdown()
        thread.join()
        dashboard_app._DATABASE_ENGINE = previous_engine

    assert response.status == 200
    assert payload["schema_version"] == 2
    assert payload["report_status"] == "grounded"
    assert payload["claims"][0]["citations"][0]["source_review_id"] == 41


def test_dashboard_search_exposes_shared_grounding_response():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    search = FakeDashboardSearch()
    previous_engine = dashboard_app._DATABASE_ENGINE
    previous_search = dashboard_app._SEARCH_ENGINE
    dashboard_app._DATABASE_ENGINE = engine
    dashboard_app._SEARCH_ENGINE = search
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1])
        body = json.dumps(
            {
                "query": "향이 어떤가요?",
                "query_embedding": [0.1, 0.2, 0.3],
                "product_id": 4,
                "limit": 6,
            },
            ensure_ascii=False,
        ).encode()
        connection.request(
            "POST",
            "/bteam/oliview/api/search",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
    finally:
        server.shutdown()
        thread.join()
        dashboard_app._DATABASE_ENGINE = previous_engine
        dashboard_app._SEARCH_ENGINE = previous_search

    assert response.status == 200
    assert payload["service"] == "dashboard_backend"
    assert payload["citations"][0]["source_review_id"] == 41
    assert search.payloads[0]["product_id"] == 4
