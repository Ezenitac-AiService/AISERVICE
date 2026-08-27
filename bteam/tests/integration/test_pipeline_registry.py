from datetime import UTC, datetime
from typing import Any, cast

import pytest
from oliview_core.cache.redis_manager import CacheVersionManager
from oliview_core.db.orm import (
    AnalysisCategoryAttribute,
    Base,
    Category,
    Product,
    ProductCategory,
    ProductReport,
    ProductReportCitationORM,
    ProductReportClaimORM,
    Review,
    ReviewPreprocessing,
    ReviewSentence,
    SentimentAnalysis,
)
from oliview_core.gateway import GatewayPool
from oliview_core.vector import ChromaVectorClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipelines.pipeline_runner import PipelineRunner
from pipelines.runtime import PipelineDependencies, PipelineStageRegistry


class FakeChroma:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def collection_id(self) -> str:
        return "green-v2"

    def upsert(self, **payload: Any) -> None:
        self.upserts.append(payload)


class FakeSplitter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def extract(
        self, review_text: str, aspect_mapping: dict[str, str]
    ) -> list[dict[str, str | int | float]]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("splitter failed")
        model_aspect = next(iter(aspect_mapping.values()))
        return [
            {
                "aspect": "사용감",
                "model_aspect": model_aspect,
                "aspect_phrase": review_text,
                "start": 0,
                "end": len(review_text),
                "confidence": 0.91,
            }
        ]


class FakeSentiment:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def predict_many(self, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("sentiment failed")
        return [
            {
                "aspect_sentence_id": row["aspect_sentence_id"],
                "sentiment_label": "긍정",
                "confidence_score": 0.88,
            }
            for row in rows
        ]


class FakeReportGenerator:
    def __init__(
        self, *, invalid_quote: bool = False, invalid_suggestion: bool = False
    ) -> None:
        self.invalid_quote = invalid_quote
        self.invalid_suggestion = invalid_suggestion
        self.calls = 0

    def generate(
        self, product_id: int, rows: list[dict[str, object]]
    ) -> dict[str, object]:
        self.calls += 1
        quote = "다른 상품의 후기" if self.invalid_quote else "발림성이 좋아요"
        return {
            "overall_summary": "발림성이 좋다는 평가가 있습니다.",
            "attributes": [
                {
                    "analysis_category_id": 10,
                    "display_name": "사용감",
                    "positive_summary": "발림성이 좋다는 평가",
                    "negative_summary": "",
                }
            ],
            "claims": [
                {
                    "claim_key": "texture-positive",
                    "claim_kind": "praise",
                    "claim_text": "발림성이 좋다는 평가가 있습니다.",
                    "citations": [{"source_review_id": 1, "quote": quote}],
                }
            ],
            "improvement_suggestions": (
                [
                    {
                        "suggestion_id": "s1",
                        "text": "개선",
                        "basis_claim_ids": ["missing"],
                    }
                ]
                if self.invalid_suggestion
                else []
            ),
            "product_id": product_id,
            "row_count": len(rows),
        }


class FakeCrawler:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[int, str]] = []

    def fetch(
        self, product_id: int, product_code: str, since: datetime
    ) -> dict[str, object]:
        self.calls.append((product_id, product_code))
        if self.fail:
            raise RuntimeError("crawler failed")
        return {
            "product": {"product_name": "updated product"},
            "reviews": [
                {
                    "review_id": 2,
                    "review_code": 202,
                    "review_content": "새 리뷰입니다.",
                    "review_score": 4,
                    "review_date": "2026-08-27",
                }
            ],
        }


def seed_category(session: Session, product_id: int = 1) -> None:
    session.add(Category(category_id=10, category_name="스킨케어"))
    session.add(ProductCategory(product_id=product_id, category_id=10))
    session.add(
        AnalysisCategoryAttribute(
            analysis_category_id=10,
            model_attribute_name="texture",
            display_name="사용감",
            display_order=1,
        )
    )


def test_registry_wires_all_five_stages_to_one_green_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(
                product_id=1,
                product_code="A000000189181",
                product_name="Green test product",
            )
        )
        session.add(
            Review(
                review_id=1,
                review_code=1,
                product_id=1,
                review_content="테스트 리뷰",
                review_score=5,
            )
        )
        session.commit()

        dependencies = PipelineDependencies(
            session=session,
            chroma=cast(ChromaVectorClient, FakeChroma()),
            cache=CacheVersionManager(app_run_mode="DEMO"),
            gateway=GatewayPool([{"url": "http://gateway-green", "healthy": True}]),
            crawler=FakeCrawler(),
            sentence_splitter=FakeSplitter(),
        )
        handlers = PipelineStageRegistry(dependencies).handlers()
        runner = PipelineRunner(step_handlers=handlers)

        result = runner.run_once(selector="product:1", steps="all")

    assert set(handlers) == {"crawl", "sentence_split", "sentiment", "report", "index"}
    assert result.completed == set(handlers)
    assert set(result.metadata["stage_results"]) == set(handlers)
    assert result.metadata["stage_results"]["index"]["collection_id"] == "green-v2"


def test_index_upserts_embeddings_then_marks_only_completed_review_products():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(
                product_id=1,
                product_code="A000000189181",
                product_name="Green test product",
            )
        )
        session.add(
            Review(
                review_id=1,
                review_code=1,
                product_id=1,
                review_content="고정된 문장",
                review_score=5,
                sentiment_analyzed_at=datetime.now(UTC),
            )
        )
        session.add(
            ReviewSentence(
                aspect_sentence_id=101,
                review_id=1,
                separated_sentence="고정된 문장",
                embedding_vector=[0.1, 0.2, 0.3],
                sentiment_label="positive",
            )
        )
        session.commit()

        fake_chroma = FakeChroma()
        cache = CacheVersionManager(app_run_mode="DEMO")
        dependencies = PipelineDependencies(
            session=session,
            chroma=cast(ChromaVectorClient, fake_chroma),
            cache=cache,
            gateway=None,
        )
        result = PipelineRunner(
            step_handlers=PipelineStageRegistry(dependencies).handlers()
        ).run_once(selector="product:1", steps="index")

        refreshed = session.get(Review, 1)
        assert refreshed is not None and refreshed.vector_indexed is True

    assert len(fake_chroma.upserts) == 1
    assert fake_chroma.upserts[0]["ids"] == ["101"]
    assert result.metadata["stage_results"]["index"]["indexed_reviews"] == 1
    assert cache.rag_version == 2


def test_sentence_split_uses_model_and_commits_one_review_batch():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Product(product_id=1, product_code="P1", product_name="p"))
        seed_category(session)
        session.add(
            Review(
                review_id=1,
                review_code=101,
                product_id=1,
                review_content="발림성이 좋아요",
                preprocessed_at=datetime.now(UTC),
            )
        )
        session.add(
            ReviewPreprocessing(review_id=1, cleaned_content="발림성이 좋아요")
        )
        session.commit()
        splitter = FakeSplitter()
        dependencies = PipelineDependencies(
            session=session,
            chroma=None,
            cache=CacheVersionManager(app_run_mode="DEMO"),
            gateway=None,
            sentence_splitter=splitter,
        )

        result = PipelineRunner(
            step_handlers=PipelineStageRegistry(dependencies).handlers()
        ).run_once(selector="product:1", steps="sentence_split")

        review = session.get(Review, 1)
        sentence = session.get(ReviewSentence, 1)

    assert splitter.calls == 1
    assert review is not None and review.aspect_split_at is not None
    assert sentence is not None
    assert sentence.model_attribute_name == "texture"
    assert sentence.display_name == "사용감"
    assert result.metadata["stage_results"]["sentence_split"]["processed_reviews"] == 1


def test_sentence_split_rolls_back_model_failure_without_timestamp():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Product(product_id=1, product_code="P1", product_name="p"))
        seed_category(session)
        session.add(
            Review(
                review_id=1,
                review_code=101,
                product_id=1,
                review_content="실패 리뷰",
                preprocessed_at=datetime.now(UTC),
            )
        )
        session.add(ReviewPreprocessing(review_id=1, cleaned_content="실패 리뷰"))
        session.commit()
        dependencies = PipelineDependencies(
            session=session,
            chroma=None,
            cache=CacheVersionManager(app_run_mode="DEMO"),
            gateway=None,
            sentence_splitter=FakeSplitter(fail=True),
        )

        with pytest.raises(RuntimeError, match="splitter failed"):
            PipelineRunner(
                step_handlers=PipelineStageRegistry(dependencies).handlers()
            ).run_once(selector="product:1", steps="sentence_split")

        review = session.get(Review, 1)
        sentence_count = session.query(ReviewSentence).count()

    assert review is not None and review.aspect_split_at is None
    assert sentence_count == 0


def test_sentiment_uses_model_and_commits_result_with_review_timestamp():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Product(product_id=1, product_code="P1", product_name="p"))
        session.add(
            Review(
                review_id=1,
                review_code=101,
                product_id=1,
                review_content="발림성이 좋아요",
                aspect_split_at=datetime.now(UTC),
            )
        )
        session.add(
            ReviewSentence(
                aspect_sentence_id=11,
                review_id=1,
                analysis_category_id=10,
                model_attribute_name="texture",
                separated_sentence="발림성이 좋아요",
                sequence_no=1,
                sentence_start=0,
                sentence_end=8,
            )
        )
        session.commit()
        sentiment = FakeSentiment()
        dependencies = PipelineDependencies(
            session=session,
            chroma=None,
            cache=CacheVersionManager(app_run_mode="DEMO"),
            gateway=None,
            sentiment_analyzer=sentiment,
        )

        result = PipelineRunner(
            step_handlers=PipelineStageRegistry(dependencies).handlers()
        ).run_once(selector="product:1", steps="sentiment")

        review = session.get(Review, 1)
        stored = session.get(SentimentAnalysis, 11)

    assert sentiment.calls == 1
    assert review is not None and review.sentiment_analyzed_at is not None
    assert stored is not None and stored.sentiment_label == "긍정"
    assert result.metadata["stage_results"]["sentiment"]["processed_reviews"] == 1


def test_report_gateway_result_is_validated_and_committed_atomically():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Product(product_id=1, product_code="P1", product_name="p"))
        seed_category(session)
        session.add(
            Review(
                review_id=1,
                review_code=101,
                product_id=1,
                review_content="발림성이 좋아요",
                sentiment_analyzed_at=datetime.now(UTC),
            )
        )
        session.add(
            ReviewSentence(
                aspect_sentence_id=11,
                review_id=1,
                analysis_category_id=10,
                model_attribute_name="texture",
                separated_sentence="발림성이 좋아요",
                sequence_no=1,
                sentence_start=0,
                sentence_end=8,
                sentiment_label="긍정",
            )
        )
        session.add(SentimentAnalysis(aspect_sentence_id=11, sentiment_label="긍정"))
        session.commit()
        generator = FakeReportGenerator()
        cache = CacheVersionManager(app_run_mode="DEMO")
        dependencies = PipelineDependencies(
            session=session,
            chroma=None,
            cache=cache,
            gateway=GatewayPool([{"url": "http://gateway-green", "healthy": True}]),
            report_generator=generator,
        )

        result = PipelineRunner(
            step_handlers=PipelineStageRegistry(dependencies).handlers()
        ).run_once(selector="product:1", steps="report")

        report = session.query(ProductReport).one()
        claim = session.query(ProductReportClaimORM).one()
        citation = session.query(ProductReportCitationORM).one()

    assert generator.calls == 1
    assert report.report_status == "grounded"
    assert claim.claim_key == "texture-positive"
    assert citation.source_review_id == 1
    assert result.metadata["stage_results"]["report"]["generated_reports"] == 1
    assert cache.report_version == 2


def test_report_invalid_citation_rolls_back_without_cache_bump():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Product(product_id=1, product_code="P1", product_name="p"))
        seed_category(session)
        session.add(
            Review(
                review_id=1,
                review_code=101,
                product_id=1,
                review_content="발림성이 좋아요",
                sentiment_analyzed_at=datetime.now(UTC),
            )
        )
        session.add(
            ReviewSentence(
                aspect_sentence_id=11,
                review_id=1,
                analysis_category_id=10,
                model_attribute_name="texture",
                separated_sentence="발림성이 좋아요",
                sequence_no=1,
                sentence_start=0,
                sentence_end=8,
                sentiment_label="긍정",
            )
        )
        session.add(SentimentAnalysis(aspect_sentence_id=11, sentiment_label="긍정"))
        session.commit()
        cache = CacheVersionManager(app_run_mode="DEMO")
        dependencies = PipelineDependencies(
            session=session,
            chroma=None,
            cache=cache,
            gateway=GatewayPool([{"url": "http://gateway-green", "healthy": True}]),
            report_generator=FakeReportGenerator(invalid_quote=True),
        )

        with pytest.raises(RuntimeError, match="citation"):
            PipelineRunner(
                step_handlers=PipelineStageRegistry(dependencies).handlers()
            ).run_once(selector="product:1", steps="report")

        assert session.query(ProductReport).count() == 0

    assert cache.report_version == 1


def test_report_invalid_suggestion_basis_rolls_back_without_cache_bump():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Product(product_id=1, product_code="P1", product_name="p"))
        seed_category(session)
        session.add(
            Review(
                review_id=1,
                review_code=101,
                product_id=1,
                review_content="발림성이 좋아요",
                sentiment_analyzed_at=datetime.now(UTC),
            )
        )
        session.add(
            ReviewSentence(
                aspect_sentence_id=11,
                review_id=1,
                analysis_category_id=10,
                model_attribute_name="texture",
                separated_sentence="발림성이 좋아요",
                sequence_no=1,
                sentence_start=0,
                sentence_end=8,
                sentiment_label="긍정",
            )
        )
        session.add(SentimentAnalysis(aspect_sentence_id=11, sentiment_label="긍정"))
        session.commit()
        cache = CacheVersionManager(app_run_mode="DEMO")
        dependencies = PipelineDependencies(
            session=session,
            chroma=None,
            cache=cache,
            gateway=GatewayPool([{"url": "http://gateway-green", "healthy": True}]),
            report_generator=FakeReportGenerator(invalid_suggestion=True),
        )

        with pytest.raises(RuntimeError, match="suggestion"):
            PipelineRunner(
                step_handlers=PipelineStageRegistry(dependencies).handlers()
            ).run_once(selector="product:1", steps="report")

        assert session.query(ProductReport).count() == 0

    assert cache.report_version == 1


def test_crawl_upserts_reviews_and_preprocessing_in_one_batch():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(
                product_id=1,
                product_code="P1",
                product_name="old product",
                review_checked_at=datetime(2026, 8, 1, tzinfo=UTC),
            )
        )
        session.commit()
        crawler = FakeCrawler()
        dependencies = PipelineDependencies(
            session=session,
            chroma=None,
            cache=CacheVersionManager(app_run_mode="DEMO"),
            gateway=None,
            crawler=crawler,
        )

        result = PipelineRunner(
            step_handlers=PipelineStageRegistry(dependencies).handlers()
        ).run_once(selector="product:1", steps="crawl")

        product = session.get(Product, 1)
        review = session.get(Review, 2)
        preprocessing = session.get(ReviewPreprocessing, 2)

    assert crawler.calls == [(1, "P1")]
    assert product is not None and product.product_name == "updated product"
    assert product.review_checked_at is not None
    assert review is not None and review.review_code == 202
    assert preprocessing is not None and preprocessing.cleaned_content == "새 리뷰입니다."
    assert result.metadata["stage_results"]["crawl"]["inserted_reviews"] == 1


def test_crawl_failure_rolls_back_review_and_product_watermark():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    original_checked_at = datetime(2026, 8, 1, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            Product(
                product_id=1,
                product_code="P1",
                product_name="old product",
                review_checked_at=original_checked_at,
            )
        )
        session.commit()
        dependencies = PipelineDependencies(
            session=session,
            chroma=None,
            cache=CacheVersionManager(app_run_mode="DEMO"),
            gateway=None,
            crawler=FakeCrawler(fail=True),
        )

        with pytest.raises(RuntimeError, match="crawler failed"):
            PipelineRunner(
                step_handlers=PipelineStageRegistry(dependencies).handlers()
            ).run_once(selector="product:1", steps="crawl")

        product = session.get(Product, 1)
        review_count = session.query(Review).count()

    assert (
        product is not None
        and product.review_checked_at is not None
        and product.review_checked_at.replace(tzinfo=UTC) == original_checked_at
    )
    assert review_count == 0
