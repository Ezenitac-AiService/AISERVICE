"""Green pipeline stage registry and dependency boundary.

The registry keeps orchestration independent from the stage implementations.  A
validation run may inspect the restored data plane, but a stage that needs an
unavailable model gateway or vector writer fails closed instead of recording a
false success checkpoint.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from oliview_core.cache.redis_manager import CacheVersionManager, RedisCachePublisher
from oliview_core.gateway import GatewayEndpoint, GatewayPool
from oliview_core.guardrails.pii_filter import mask_pii
from oliview_core.guardrails.sanitizer import normalize_quote
from oliview_core.reports import validate_report
from oliview_core.vector import ChromaVectorClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .pipeline_runner import PipelineContext
from .pipeline_selection import CANONICAL_STEPS


class StageDependencyError(RuntimeError):
    """Raised when a configured stage cannot reach a required dependency."""


StageHandler = Callable[[PipelineContext], None]


@dataclass(frozen=True)
class PipelineDependencies:
    session: Session
    chroma: ChromaVectorClient | None
    cache: CacheVersionManager
    gateway: GatewayPool | None
    batch_size: int = 500
    crawler: Any | None = None
    crawler_factory: Callable[[], Any] | None = None
    sentence_splitter: Any | None = None
    sentence_splitter_factory: Callable[[], Any] | None = None
    sentiment_analyzer: Any | None = None
    sentiment_analyzer_factory: Callable[[], Any] | None = None
    report_generator: Any | None = None
    report_generator_factory: Callable[[], Any] | None = None


class PipelineStageRegistry:
    """Build the canonical five stage handlers around one dependency context."""

    def __init__(self, dependencies: PipelineDependencies):
        if dependencies.batch_size != 500:
            raise ValueError("pipeline batch_size must be exactly 500")
        self.dependencies = dependencies
        self._sentence_splitter = dependencies.sentence_splitter
        self._sentiment_analyzer = dependencies.sentiment_analyzer
        self._report_generator = dependencies.report_generator
        self._crawler = dependencies.crawler

    def handlers(self) -> dict[str, StageHandler]:
        return {
            "crawl": self.crawl,
            "sentence_split": self.sentence_split,
            "sentiment": self.sentiment,
            "report": self.report,
            "index": self.index,
        }

    def _product_ids(self, context: PipelineContext) -> list[int]:
        selector = context.selector
        session = self.dependencies.session
        if selector.startswith("product:"):
            product_id = int(selector.split(":", 1)[1])
            rows = session.execute(
                text("SELECT product_id FROM products WHERE product_id = :product_id"),
                {"product_id": product_id},
            ).scalars().all()
            if not rows:
                raise StageDependencyError(f"product not found: {product_id}")
            return [int(rows[0])]
        if selector.startswith("product_code:"):
            product_code = selector.split(":", 1)[1]
            rows = session.execute(
                text("SELECT product_id FROM products WHERE product_code = :product_code"),
                {"product_code": product_code},
            ).scalars().all()
            if not rows:
                raise StageDependencyError(f"product code not found: {product_code}")
            return [int(rows[0])]
        if selector in {"cycle", "all-products"}:
            rows = session.execute(
                text("SELECT product_id FROM products WHERE is_active = 1 ORDER BY product_id")
            ).scalars().all()
            return [int(value) for value in rows]
        raise StageDependencyError(f"unsupported pipeline selector: {selector}")

    @staticmethod
    def _as_int(value: object) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError) as error:
            raise StageDependencyError(f"invalid database integer: {value}") from error

    def _count(self, query: str, params: dict[str, Any]) -> int:
        value = self.dependencies.session.execute(text(query), params).scalar_one()
        return int(value or 0)

    def _product_filter(self, product_ids: list[int]) -> tuple[str, dict[str, int]]:
        if not product_ids:
            raise StageDependencyError("pipeline selector resolved to no products")
        placeholders = ",".join(
            f":product_{index}" for index in range(len(product_ids))
        )
        return placeholders, {
            f"product_{index}": product_id
            for index, product_id in enumerate(product_ids)
        }

    def _category_aspects(
        self, product_ids: list[int]
    ) -> dict[int, list[dict[str, object]]]:
        placeholders, params = self._product_filter(product_ids)
        rows = self.dependencies.session.execute(
            text(
                "WITH RECURSIVE category_ancestors AS ("
                " SELECT pc.product_id, c.category_id, c.parent_category_id "
                " FROM product_categories pc "
                " JOIN categories c ON c.category_id = pc.category_id "
                f" WHERE pc.product_id IN ({placeholders}) "
                " UNION ALL "
                " SELECT ca.product_id, parent.category_id, parent.parent_category_id "
                " FROM category_ancestors ca "
                " JOIN categories parent ON parent.category_id = ca.parent_category_id "
                " WHERE ca.parent_category_id IS NOT NULL "
                " AND ca.product_id IN (" + placeholders + ")"
                ") SELECT DISTINCT ca.product_id, aca.analysis_category_id, "
                "aca.display_name, aca.model_attribute_name, aca.display_order "
                "FROM category_ancestors ca "
                "JOIN analysis_category_attributes aca "
                " ON aca.analysis_category_id = ca.category_id "
                "ORDER BY ca.product_id, aca.analysis_category_id, aca.display_order"
            ),
            params,
        ).mappings().all()
        if not rows:
            return {}
        result: dict[int, list[dict[str, object]]] = {}
        for row in rows:
            result.setdefault(int(row["product_id"]), []).append(dict(row))
        return result

    def _candidate_reviews(
        self, product_ids: list[int], *, require_split: bool
    ) -> list[dict[str, object]]:
        placeholders, params = self._product_filter(product_ids)
        split_clause = (
            "r.aspect_split_at IS NULL AND r.preprocessed_at IS NOT NULL "
            "AND rp.cleaned_content IS NOT NULL AND TRIM(rp.cleaned_content) <> ''"
            if require_split
            else "r.aspect_split_at IS NOT NULL AND r.sentiment_analyzed_at IS NULL"
        )
        join = (
            "JOIN review_preprocessing rp ON rp.review_id = r.review_id"
            if require_split
            else ""
        )
        content = ", rp.cleaned_content" if require_split else ""
        return [
            dict(row)
            for row in self.dependencies.session.execute(
                text(
                    "SELECT r.review_id, r.product_id"
                    + content
                    + " FROM reviews r "
                    + join
                    + f" WHERE r.product_id IN ({placeholders}) AND {split_clause}"
                    + " ORDER BY r.review_id LIMIT 500"
                ),
                params,
            ).mappings().all()
        ]

    def _load_splitter(self) -> Any:
        splitter = self._sentence_splitter
        if splitter is not None:
            return splitter
        factory = self.dependencies.sentence_splitter_factory
        if factory is None:
            raise StageDependencyError(
                "sentence_split model adapter is not configured"
            )
        try:
            splitter = factory()
        except Exception as error:
            raise StageDependencyError(
                "sentence_split model adapter is unavailable"
            ) from error
        self._sentence_splitter = splitter
        return splitter

    def _load_sentiment_analyzer(self) -> Any:
        analyzer = self._sentiment_analyzer
        if analyzer is not None:
            return analyzer
        factory = self.dependencies.sentiment_analyzer_factory
        if factory is None:
            raise StageDependencyError("sentiment model adapter is not configured")
        try:
            analyzer = factory()
        except Exception as error:
            raise StageDependencyError("sentiment model adapter is unavailable") from error
        self._sentiment_analyzer = analyzer
        return analyzer

    def _load_report_generator(self) -> Any:
        generator = self._report_generator
        if generator is not None:
            return generator
        factory = self.dependencies.report_generator_factory
        if factory is None:
            raise StageDependencyError("report model Gateway adapter is not configured")
        try:
            generator = factory()
        except Exception as error:
            raise StageDependencyError("report model Gateway adapter is unavailable") from error
        self._report_generator = generator
        return generator

    def _load_crawler(self) -> Any:
        crawler = self._crawler
        if crawler is not None:
            return crawler
        factory = self.dependencies.crawler_factory
        if factory is None:
            raise StageDependencyError("review crawler adapter is not configured")
        try:
            crawler = factory()
        except Exception as error:
            raise StageDependencyError("review crawler adapter is unavailable") from error
        self._crawler = crawler
        return crawler

    def _record(self, context: PipelineContext, step: str, **values: object) -> None:
        results = context.metadata.setdefault("stage_results", {})
        if not isinstance(results, dict):
            raise StageDependencyError("pipeline stage_results metadata is invalid")
        results[step] = {"batch_size": self.dependencies.batch_size, **values}

    def crawl(self, context: PipelineContext) -> None:
        from datetime import UTC, date, datetime

        from oliview_core.db.orm import Product, Review, ReviewPreprocessing

        product_ids = self._product_ids(context)
        placeholders, params = self._product_filter(product_ids)
        due = self._count(
            "SELECT COUNT(*) FROM products "
            f"WHERE is_active = 1 AND product_id IN ({placeholders}) "
            "AND (review_checked_at IS NULL OR review_checked_at <= :watermark)",
            {**params, "watermark": context.cycle_watermark},
        )
        if due == 0:
            self._record(
                context,
                "crawl",
                product_count=len(product_ids),
                due_products=0,
                inserted_reviews=0,
                updated_reviews=0,
                crawler="not_required",
            )
            return

        crawler = self._load_crawler()
        products = self.dependencies.session.execute(
            select(Product)
            .where(Product.product_id.in_(product_ids), Product.is_active.is_(True))
            .where(
                (Product.review_checked_at.is_(None))
                | (Product.review_checked_at <= context.cycle_watermark)
            )
            .order_by(Product.product_id)
            .limit(self.dependencies.batch_size)
        ).scalars().all()
        inserted = 0
        updated = 0
        now = datetime.now(UTC)
        try:
            for product in products:
                response = crawler.fetch(
                    int(product.product_id),
                    str(product.product_code),
                    context.cycle_watermark,
                )
                if not isinstance(response, Mapping):
                    raise StageDependencyError("review crawler response must be an object")
                product_payload = response.get("product")
                if isinstance(product_payload, Mapping):
                    product_name = product_payload.get("product_name")
                    if product_name is not None:
                        product.product_name = str(product_name)
                raw_reviews = response.get("reviews", [])
                if not isinstance(raw_reviews, list):
                    raise StageDependencyError("review crawler reviews must be a list")
                for raw_review in raw_reviews[: self.dependencies.batch_size]:
                    if not isinstance(raw_review, Mapping):
                        raise StageDependencyError("review crawler review must be an object")
                    raw_code = raw_review.get("review_code")
                    review_code = int(raw_code) if raw_code is not None else None
                    raw_id = raw_review.get("review_id")
                    review_id = int(raw_id) if raw_id is not None else None
                    content_value = raw_review.get(
                        "review_content", raw_review.get("content")
                    )
                    if content_value is None or not str(content_value).strip():
                        raise StageDependencyError("review crawler review content is required")
                    raw_content = str(content_value)
                    safe_content = mask_pii(raw_content)
                    review = self.dependencies.session.get(Review, review_id) if review_id else None
                    if review is None and review_code is not None:
                        review = self.dependencies.session.scalar(
                            select(Review).where(Review.review_code == review_code)
                        )
                    if review is not None and int(review.product_id) != int(product.product_id):
                        raise StageDependencyError("review belongs to another product")
                    raw_date = raw_review.get("review_date")
                    if isinstance(raw_date, date):
                        review_date = raw_date
                    elif raw_date:
                        review_date = date.fromisoformat(str(raw_date)[:10])
                    else:
                        review_date = datetime.now(UTC).date()
                    score_value = raw_review.get("review_score", 0)
                    if review is None:
                        review = Review(
                            review_id=review_id,
                            review_code=review_code,
                            product_id=int(product.product_id),
                            product_option_id=(
                                int(raw_review["product_option_id"])
                                if raw_review.get("product_option_id") is not None
                                else None
                            ),
                            review_content=raw_content,
                            review_score=int(score_value or 0),
                            review_date=review_date,
                            collected_at=now,
                            preprocessed_at=now,
                        )
                        self.dependencies.session.add(review)
                        self.dependencies.session.flush()
                        inserted += 1
                        self.dependencies.session.add(
                            ReviewPreprocessing(
                                review_id=int(review.review_id),
                                cleaned_content=safe_content,
                            )
                        )
                    else:
                        content_changed = review.review_content != raw_content
                        review.review_code = review_code
                        review.review_content = raw_content
                        review.review_score = int(score_value or 0)
                        review.review_date = review_date
                        review.collected_at = now
                        if content_changed:
                            self.dependencies.session.execute(
                                text(
                                    "DELETE FROM aspect_sentiment_results "
                                    "WHERE aspect_sentence_id IN ("
                                    "SELECT aspect_sentence_id FROM review_aspect_sentences "
                                    "WHERE review_id = :review_id)"
                                ),
                                {"review_id": int(review.review_id)},
                            )
                            self.dependencies.session.execute(
                                text(
                                    "DELETE FROM review_aspect_sentences "
                                    "WHERE review_id = :review_id"
                                ),
                                {"review_id": int(review.review_id)},
                            )
                            review.preprocessed_at = now
                            review.aspect_split_at = None
                            review.sentiment_analyzed_at = None
                            review.vector_indexed = False
                        preprocessing = self.dependencies.session.get(
                            ReviewPreprocessing, int(review.review_id)
                        )
                        if preprocessing is None:
                            self.dependencies.session.add(
                                ReviewPreprocessing(
                                    review_id=int(review.review_id),
                                    cleaned_content=safe_content,
                                )
                            )
                        elif content_changed:
                            preprocessing.cleaned_content = safe_content
                        updated += 1
                product.review_checked_at = now
            self.dependencies.session.commit()
        except Exception:
            self.dependencies.session.rollback()
            raise
        self._record(
            context,
            "crawl",
            product_count=len(product_ids),
            due_products=due,
            processed_products=len(products),
            inserted_reviews=inserted,
            updated_reviews=updated,
            crawler=type(crawler).__name__,
        )

    def sentence_split(self, context: PipelineContext) -> None:
        product_ids = self._product_ids(context)
        candidates = self._candidate_reviews(product_ids, require_split=True)
        if not candidates:
            self._record(
                context,
                "sentence_split",
                pending_reviews=0,
                processed_reviews=0,
                inserted_sentences=0,
                model="not_required",
            )
            return
        splitter = self._load_splitter()
        category_aspects = self._category_aspects(
            [self._as_int(row["product_id"]) for row in candidates]
        )
        grouped: dict[int, dict[str, object]] = {}
        for row in candidates:
            grouped[self._as_int(row["review_id"])] = row
        inserted = 0
        processed = 0
        try:
            for review_id, review in grouped.items():
                category_rows = category_aspects.get(
                    self._as_int(review["product_id"]), []
                )
                if not category_rows:
                    continue
                for category_id in sorted(
                    {
                        self._as_int(item["analysis_category_id"])
                        for item in category_rows
                    }
                ):
                    category_attributes = [
                        item
                        for item in category_rows
                        if self._as_int(item["analysis_category_id"]) == category_id
                    ]
                    mapping = {
                        str(item["display_name"]): str(item["model_attribute_name"])
                        for item in category_attributes
                    }
                    extracted = splitter.extract(
                        str(review["cleaned_content"]), mapping
                    )
                    self.dependencies.session.execute(
                        text(
                            "DELETE FROM review_aspect_sentences "
                            "WHERE review_id = :review_id "
                            "AND analysis_category_id = :category_id"
                        ),
                        {"review_id": review_id, "category_id": category_id},
                    )
                    ordered = sorted(
                        extracted,
                        key=lambda item: (
                            self._as_int(item["start"]),
                            self._as_int(item["end"]),
                            str(item["model_aspect"]),
                        ),
                    )
                    for sequence_no, item in enumerate(ordered, start=1):
                        self.dependencies.session.execute(
                            text(
                                "INSERT INTO review_aspect_sentences ("
                                "review_id, analysis_category_id, model_attribute_name, "
                                "sequence_no, separated_sentence, sentence_start, "
                                "sentence_end, confidence_score, display_name"
                                ") VALUES ("
                                ":review_id, :category_id, :model_attribute_name, "
                                ":sequence_no, :sentence, :start, :end, "
                                ":confidence, :display_name)"
                            ),
                            {
                                "review_id": review_id,
                                "category_id": category_id,
                                "model_attribute_name": str(item["model_aspect"]),
                                "sequence_no": sequence_no,
                                "sentence": str(item["aspect_phrase"]),
                                "start": self._as_int(item["start"]),
                                "end": self._as_int(item["end"]),
                                "confidence": float(item["confidence"]),
                                "display_name": str(item["aspect"]),
                            },
                        )
                        inserted += 1
                self.dependencies.session.execute(
                    text(
                        "UPDATE reviews SET aspect_split_at = CURRENT_TIMESTAMP, "
                        "sentiment_analyzed_at = NULL, vector_indexed = 0 "
                        "WHERE review_id = :review_id"
                    ),
                    {"review_id": review_id},
                )
                processed += 1
            self.dependencies.session.commit()
        except Exception:
            self.dependencies.session.rollback()
            raise
        self._record(
            context,
            "sentence_split",
            pending_reviews=len(candidates),
            processed_reviews=processed,
            inserted_sentences=inserted,
            model=type(splitter).__name__,
        )

    def sentiment(self, context: PipelineContext) -> None:
        product_ids = self._product_ids(context)
        candidates = self._candidate_reviews(product_ids, require_split=False)
        if not candidates:
            self._record(
                context,
                "sentiment",
                pending_reviews=0,
                processed_reviews=0,
                stored_results=0,
                model="not_required",
            )
            return
        analyzer = self._load_sentiment_analyzer()
        review_ids = [self._as_int(row["review_id"]) for row in candidates]
        review_placeholders, review_params = self._product_filter(review_ids)
        sentence_rows = self.dependencies.session.execute(
            text(
                "SELECT review_id, aspect_sentence_id, model_attribute_name, "
                "separated_sentence FROM review_aspect_sentences "
                f"WHERE review_id IN ({review_placeholders}) ORDER BY review_id, aspect_sentence_id"
            ),
            review_params,
        ).mappings().all()
        grouped: dict[int, list[dict[str, object]]] = {review_id: [] for review_id in review_ids}
        for row in sentence_rows:
            grouped[self._as_int(row["review_id"])].append(dict(row))
        stored = 0
        try:
            for review_id in review_ids:
                rows = grouped[review_id]
                results = analyzer.predict_many(rows)
                for result in results:
                    label = self._normalize_sentiment_label(result["sentiment_label"])
                    values = {
                        "sentence_id": int(result["aspect_sentence_id"]),
                        "label": label,
                        "confidence": float(result["confidence_score"]),
                    }
                    updated = self.dependencies.session.execute(
                        text(
                            "UPDATE aspect_sentiment_results SET sentiment_label = :label, "
                            "confidence_score = :confidence "
                            "WHERE aspect_sentence_id = :sentence_id"
                        ),
                        values,
                    )
                    if getattr(updated, "rowcount", 0) == 0:
                        self.dependencies.session.execute(
                            text(
                                "INSERT INTO aspect_sentiment_results "
                                "(aspect_sentence_id, sentiment_label, confidence_score) "
                                "VALUES (:sentence_id, :label, :confidence)"
                            ),
                            values,
                        )
                    self.dependencies.session.execute(
                        text(
                            "UPDATE review_aspect_sentences SET sentiment_label = :label "
                            "WHERE aspect_sentence_id = :sentence_id"
                        ),
                        {
                            "label": label,
                            "sentence_id": int(result["aspect_sentence_id"]),
                        },
                    )
                    stored += 1
                self.dependencies.session.execute(
                    text(
                        "UPDATE reviews SET sentiment_analyzed_at = CURRENT_TIMESTAMP "
                        "WHERE review_id = :review_id"
                    ),
                    {"review_id": review_id},
                )
            self.dependencies.session.commit()
        except Exception:
            self.dependencies.session.rollback()
            raise
        self._record(
            context,
            "sentiment",
            pending_reviews=len(candidates),
            processed_reviews=len(candidates),
            stored_results=stored,
            model=type(analyzer).__name__,
        )

    @staticmethod
    def _normalize_sentiment_label(value: object) -> str:
        labels = {
            "positive": "긍정",
            "negative": "부정",
            "neutral": "중립",
            "긍정": "긍정",
            "부정": "부정",
            "중립": "중립",
        }
        normalized = labels.get(str(value).strip().casefold())
        if normalized is None:
            raise StageDependencyError(f"unsupported sentiment label: {value}")
        return normalized

    def report(self, context: PipelineContext) -> None:
        product_ids = self._product_ids(context)
        generator: Any | None = None
        generated = 0
        abstained = 0
        successful_products: list[int] = []
        try:
            for product_id in product_ids:
                rows = self.dependencies.session.execute(
                    text(
                        "SELECT ras.review_id, ras.aspect_sentence_id, "
                        "ras.analysis_category_id, ras.model_attribute_name, "
                        "aca.display_name, ras.separated_sentence, "
                        "COALESCE(ras.sentiment_label, asr.sentiment_label) AS sentiment_label, "
                        "r.review_content "
                        "FROM review_aspect_sentences ras "
                        "JOIN reviews r ON r.review_id = ras.review_id "
                        "LEFT JOIN analysis_category_attributes aca ON "
                        "aca.analysis_category_id = ras.analysis_category_id AND "
                        "aca.model_attribute_name = ras.model_attribute_name "
                        "LEFT JOIN aspect_sentiment_results asr ON "
                        "asr.aspect_sentence_id = ras.aspect_sentence_id "
                        "WHERE r.product_id = :product_id "
                        "AND r.sentiment_analyzed_at IS NOT NULL "
                        "ORDER BY ras.aspect_sentence_id LIMIT 500"
                    ),
                    {"product_id": product_id},
                ).mappings().all()
                if not rows:
                    self._persist_abstained_report(product_id, "NO_REVIEWS")
                    abstained += 1
                    successful_products.append(product_id)
                    continue
                if generator is None:
                    generator = self._load_report_generator()
                report_data = generator.generate(product_id, [dict(row) for row in rows])
                self._persist_grounded_report(product_id, report_data, [dict(row) for row in rows])
                generated += 1
                successful_products.append(product_id)
            self.dependencies.session.commit()
        except Exception:
            self.dependencies.session.rollback()
            raise
        for product_id in successful_products:
            # Report cache is advanced only after the DB transaction above has
            # committed. A publisher failure remains visible to the runner.
            self.dependencies.cache.bump(product_id, "report")
        self._record(
            context,
            "report",
            product_count=len(product_ids),
            generated_reports=generated,
            abstained_reports=abstained,
        )

    def _persist_abstained_report(self, product_id: int, reason: str) -> None:
        from datetime import UTC, datetime

        from oliview_core.db.orm import ProductReport

        self.dependencies.session.add(
            ProductReport(
                product_id=product_id,
                report_status="abstained",
                abstention_reason=reason,
                generated_at=datetime.now(UTC),
            )
        )

    def _persist_grounded_report(
        self,
        product_id: int,
        report_data: object,
        source_rows: list[dict[str, object]],
    ) -> None:
        from datetime import UTC, datetime

        from oliview_core.db.orm import (
            ProductReport,
            ProductReportAttribute,
            ProductReportCitationORM,
            ProductReportClaimORM,
        )
        from oliview_core.guardrails.pii_filter import mask_pii

        if not isinstance(report_data, dict):
            raise StageDependencyError("report Gateway payload must be an object")
        if report_data.get("product_id") is not None and self._as_int(
            report_data["product_id"]
        ) != product_id:
            raise StageDependencyError("report Gateway product_id is invalid")
        source_reviews: dict[int | str, Mapping[str, Any]] = {
            self._as_int(row["review_id"]): {
                "product_id": product_id,
                "review_content": str(row["review_content"]),
            }
            for row in source_rows
        }
        raw_claims = report_data.get("claims")
        if not isinstance(raw_claims, list) or not raw_claims:
            raise StageDependencyError("report Gateway returned no grounded claims")
        claims: list[dict[str, object]] = []
        for raw_claim in raw_claims:
            if not isinstance(raw_claim, dict):
                raise StageDependencyError("report claim must be an object")
            claim_key = str(raw_claim.get("claim_key", "")).strip()
            claim_kind = str(raw_claim.get("claim_kind", "observation")).strip()
            claim_text = str(raw_claim.get("claim_text", "")).strip()
            raw_citations = raw_claim.get("citations")
            if not claim_key or not claim_text or not isinstance(raw_citations, list):
                raise StageDependencyError("report claim fields are incomplete")
            citations: list[dict[str, object]] = []
            for raw_citation in raw_citations:
                if not isinstance(raw_citation, dict):
                    raise StageDependencyError("report citation must be an object")
                source_id = self._as_int(raw_citation.get("source_review_id"))
                quote = str(raw_citation.get("quote", "")).strip()
                if source_id not in source_reviews:
                    raise StageDependencyError("report citation source review is invalid")
                if mask_pii(quote) != quote:
                    raise StageDependencyError("report citation contains PII")
                if normalize_quote(quote).casefold() not in normalize_quote(
                    str(source_reviews[source_id]["review_content"])
                ).casefold():
                    raise StageDependencyError("report citation quote is not a source substring")
                citations.append({"source_review_id": source_id, "quote": quote})
            if not citations:
                raise StageDependencyError("grounded report claims require citations")
            claims.append(
                {
                    "claim_key": claim_key,
                    "claim_kind": claim_kind,
                    "claim_text": claim_text,
                    "citations": citations,
                }
            )
        keys = {str(claim["claim_key"]) for claim in claims}
        raw_suggestions = report_data.get("improvement_suggestions", [])
        if raw_suggestions is None:
            raw_suggestions = []
        if not isinstance(raw_suggestions, list):
            raise StageDependencyError("report suggestions must be a list")
        suggestions: list[dict[str, object]] = []
        for raw_suggestion in raw_suggestions:
            if not isinstance(raw_suggestion, dict):
                raise StageDependencyError("report suggestion must be an object")
            suggestion_id = str(raw_suggestion.get("suggestion_id", "")).strip()
            suggestion_text = str(raw_suggestion.get("text", "")).strip()
            raw_basis = raw_suggestion.get("basis_claim_ids")
            if (
                not suggestion_id
                or not suggestion_text
                or not isinstance(raw_basis, list)
                or not raw_basis
            ):
                raise StageDependencyError("report suggestion fields are incomplete")
            basis_claim_ids = [str(value) for value in raw_basis]
            if any(value not in keys for value in basis_claim_ids):
                raise StageDependencyError("suggestion basis claim does not exist")
            suggestions.append(
                {
                    "suggestion_id": suggestion_id,
                    "text": suggestion_text,
                    "basis_claim_ids": basis_claim_ids,
                }
            )
        normalized_report = {
            "product_id": product_id,
            "report_status": "grounded",
            "claims": [
                {
                    "claim_id": str(claim["claim_key"]),
                    "claim_type": str(claim["claim_kind"]),
                    "text": str(claim["claim_text"]),
                    "citations": claim["citations"],
                }
                for claim in claims
            ],
            "key_complaints": [
                str(claim["claim_key"])
                for claim in claims
                if str(claim["claim_kind"]) == "complaint"
            ],
            "key_praises": [
                str(claim["claim_key"])
                for claim in claims
                if str(claim["claim_kind"]) == "praise"
            ],
            "improvement_suggestions": suggestions,
        }
        try:
            validate_report(normalized_report, reviews=source_reviews)
        except (TypeError, ValueError) as error:
            raise StageDependencyError("report citation validation failed") from error
        report = ProductReport(
            product_id=product_id,
            report_status="grounded",
            abstention_reason=None,
            overall_summary=str(report_data.get("overall_summary", "")),
            keep_summary=(
                str(report_data["keep_summary"])
                if report_data.get("keep_summary") is not None
                else None
            ),
            improvement_summary=(
                str(report_data["improvement_summary"])
                if report_data.get("improvement_summary") is not None
                else None
            ),
            generated_at=datetime.now(UTC),
        )
        self.dependencies.session.add(report)
        self.dependencies.session.flush()
        for order, claim in enumerate(claims):
            claim_row = ProductReportClaimORM(
                llm_product_report_id=report.llm_product_report_id,
                claim_key=str(claim["claim_key"]),
                claim_kind=str(claim["claim_kind"]),
                claim_text=str(claim["claim_text"]),
                sort_order=order,
            )
            self.dependencies.session.add(claim_row)
            self.dependencies.session.flush()
            citations = cast(list[dict[str, object]], claim["citations"])
            for citation_order, citation in enumerate(citations):
                citation = dict(citation)
                self.dependencies.session.add(
                    ProductReportCitationORM(
                        report_claim_id=claim_row.report_claim_id,
                        source_review_id=self._as_int(citation["source_review_id"]),
                        quote_text=str(citation.get("quote", "")),
                        sort_order=citation_order,
                    )
                )
        for raw_attribute in report_data.get("attributes", []):
            if not isinstance(raw_attribute, dict):
                raise StageDependencyError("report attribute must be an object")
            category_id = self._as_int(raw_attribute.get("analysis_category_id"))
            display_name = str(raw_attribute.get("display_name", "")).strip()
            if not display_name:
                raise StageDependencyError("report attribute display name is required")
            exists = self.dependencies.session.execute(
                text(
                    "SELECT 1 FROM analysis_category_attributes "
                    "WHERE analysis_category_id = :category_id AND display_name = :display_name LIMIT 1"
                ),
                {"category_id": category_id, "display_name": display_name},
            ).first()
            if exists is None:
                raise StageDependencyError("report attribute is not configured")
            self.dependencies.session.add(
                ProductReportAttribute(
                    llm_product_report_id=report.llm_product_report_id,
                    product_id=product_id,
                    analysis_category_id=category_id,
                    display_name=display_name,
                    positive_summary=(
                        str(raw_attribute["positive_summary"])
                        if raw_attribute.get("positive_summary") is not None
                        else None
                    ),
                    negative_summary=(
                        str(raw_attribute["negative_summary"])
                        if raw_attribute.get("negative_summary") is not None
                        else None
                    ),
                    generated_at=datetime.now(UTC),
                )
            )

    def index(self, context: PipelineContext) -> None:
        chroma = self.dependencies.chroma
        if chroma is None:
            raise StageDependencyError("Chroma v2 writer is not configured for index")
        collection_id = chroma.collection_id()
        product_ids = self._product_ids(context)
        placeholders = ",".join(f":product_{index}" for index in range(len(product_ids)))
        params = {
            f"product_{index}": product_id
            for index, product_id in enumerate(product_ids)
        }
        rows = self.dependencies.session.execute(
            text(
                "SELECT ras.aspect_sentence_id, ras.review_id AS source_review_id, "
                "r.product_id, ras.separated_sentence, ras.embedding_vector "
                "FROM review_aspect_sentences ras "
                "JOIN reviews r ON r.review_id = ras.review_id "
                f"WHERE r.product_id IN ({placeholders}) "
                "AND r.vector_indexed = 0 "
                "AND r.sentiment_analyzed_at IS NOT NULL "
                "AND ras.embedding_vector IS NOT NULL "
                "ORDER BY ras.aspect_sentence_id LIMIT 500"
            ),
            params,
        ).mappings().all()
        ids: list[str] = []
        embeddings: list[list[float]] = []
        documents: list[str] = []
        metadatas: list[dict[str, object]] = []
        rows_by_review: dict[int, int] = {}
        review_products: dict[int, int] = {}
        for row in rows:
            raw_embedding = row["embedding_vector"]
            embedding = (
                json.loads(str(raw_embedding))
                if isinstance(raw_embedding, str)
                else raw_embedding
            )
            if not isinstance(embedding, list) or not embedding:
                continue
            source_review_id = int(row["source_review_id"])
            product_id = int(row["product_id"])
            ids.append(str(row["aspect_sentence_id"]))
            embeddings.append([float(value) for value in embedding])
            documents.append(mask_pii(str(row["separated_sentence"])))
            metadatas.append(
                {
                    "source_review_id": source_review_id,
                    "review_id": source_review_id,
                    "product_id": product_id,
                    "aspect_sentence_id": int(row["aspect_sentence_id"]),
                }
            )
            rows_by_review[source_review_id] = rows_by_review.get(source_review_id, 0) + 1
            review_products[source_review_id] = product_id
        if ids:
            chroma.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
                max_attempts=3,
            )
        complete_review_ids: list[int] = []
        for review_id, batch_count in rows_by_review.items():
            total_count = self._count(
                "SELECT COUNT(*) FROM review_aspect_sentences "
                "WHERE review_id = :review_id AND embedding_vector IS NOT NULL",
                {"review_id": review_id},
            )
            if total_count == batch_count:
                complete_review_ids.append(review_id)
        if complete_review_ids:
            review_placeholders = ",".join(
                f":review_{index}" for index in range(len(complete_review_ids))
            )
            self.dependencies.session.execute(
                text(
                    "UPDATE reviews SET vector_indexed = 1 "
                    f"WHERE review_id IN ({review_placeholders})"
                ),
                {
                    f"review_{index}": review_id
                    for index, review_id in enumerate(complete_review_ids)
                },
            )
            for product_id in sorted(
                {review_products[review_id] for review_id in complete_review_ids}
            ):
                self.dependencies.cache.bump(product_id, "rag")
        self._record(
            context,
            "index",
            collection_id=collection_id,
            indexed_sentences=len(ids),
            indexed_reviews=len(complete_review_ids),
            cache_version=self.dependencies.cache.rag_version,
        )


def build_green_handlers(session: Session) -> dict[str, StageHandler]:
    """Create the Green registry from allowlisted runtime environment values."""
    from oliview_core.config import Settings

    from .report_generator.report_runner import GatewayReportGenerator
    from .sentence_split.split_runner import TransformerSentenceSplitter
    from .sentiment.sentiment_runner import TransformerSentimentAnalyzer

    settings = Settings.from_env()
    chroma_endpoint = settings.chroma_write_endpoint.strip()
    crawler_endpoint = settings.crawler_endpoint.strip()
    chroma = ChromaVectorClient(chroma_endpoint) if chroma_endpoint else None
    gateway: GatewayPool | None = None
    raw_endpoints = settings.model_gateway_endpoints
    crawler_factory: Callable[[], Any] | None = None
    if crawler_endpoint:
        from .crawler.crawler_runner import JsonReviewCrawler

        crawler_factory = lambda endpoint=crawler_endpoint: JsonReviewCrawler(endpoint)
    report_generator_factory: Callable[[], Any] | None = None
    try:
        endpoint_values = json.loads(raw_endpoints)
        if isinstance(endpoint_values, list):
            gateway = GatewayPool(
                [GatewayEndpoint.from_mapping(value) for value in endpoint_values]
            )
            if endpoint_values:
                report_generator_factory = lambda values=endpoint_values: GatewayReportGenerator(
                    values,
                    os.getenv("REPORT_MODEL", "oliview-report"),
                )
    except (TypeError, ValueError, json.JSONDecodeError):
        gateway = None
    dependencies = PipelineDependencies(
        session=session,
        chroma=chroma,
        cache=CacheVersionManager(
            app_run_mode=os.getenv("APP_RUN_MODE", "DEMO"),
            publisher=(
                RedisCachePublisher(redis_endpoint)
                if (redis_endpoint := os.getenv("REDIS_ENDPOINT", "").strip())
                else None
            ),
        ),
        gateway=gateway,
        crawler_factory=crawler_factory,
        sentence_splitter_factory=lambda: TransformerSentenceSplitter(
            os.getenv(
                "SENTENCE_SPLIT_MODEL_DIR", "/models/sentence_split/aspect_span_extractor"
            )
        ),
        sentiment_analyzer_factory=lambda: TransformerSentimentAnalyzer(
            os.getenv(
                "SENTIMENT_MODEL_DIR", "/models/sentiment/aspect_26_all_categories_v2"
            )
        ),
        report_generator_factory=report_generator_factory,
    )
    handlers = PipelineStageRegistry(dependencies).handlers()
    if set(handlers) != set(CANONICAL_STEPS):
        raise StageDependencyError("canonical pipeline handler registry is incomplete")
    return handlers
