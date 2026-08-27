from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from oliview_core.db.orm import (
    AnalysisCategoryAttribute,
    Brand,
    Category,
    Product,
    ProductCategory,
    ProductReport,
    ProductReportAttribute,
    ProductReportCitationORM,
    ProductReportClaimORM,
    Review,
    ReviewSentence,
    SentimentAnalysis,
)
from oliview_core.reports import legacy_report_projection, validate_report
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

POSITIVE_LABELS = ("positive", "긍정", "1", "pos", "p", "true")
NEGATIVE_LABELS = ("negative", "부정", "0", "neg", "n", "false")
NEUTRAL_LABELS = ("neutral", "중립", "neu", "2")


def project_report(
    report: Mapping[str, Any],
    *,
    reviews: Mapping[int | str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    projected = legacy_report_projection(report)
    projected.setdefault("report_status", projected.get("status", "abstained"))
    if projected.get("report_status") == "grounded" and projected.get("claims"):
        validate_report(projected, reviews=reviews or {})
    else:
        projected["report_status"] = "abstained"
        projected["abstention_reason"] = (
            projected.get("abstention_reason") or "LEGACY_UNVERIFIED"
        )
        projected["claims"] = []
        projected["key_complaints"] = []
        projected["key_praises"] = []
        projected["improvement_suggestions"] = []
    return projected


def load_report_file(directory: str | Path, report_id: int) -> dict[str, Any] | None:
    path = Path(directory) / f"{report_id}.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("report file must contain a JSON object")
    return project_report(value)


def load_report_db(session: Session, report_id: int) -> dict[str, Any] | None:
    """Load the normalized report projection from the Green MySQL schema."""
    report = session.get(ProductReport, report_id)
    if report is None:
        return None
    product = session.get(Product, report.product_id)
    if product is None:
        raise ValueError("report product does not exist")

    brand_name = ""
    if product.brand_id is not None:
        brand = session.get(Brand, product.brand_id)
        brand_name = brand.brand_name if brand is not None else ""
    category_names = session.scalars(
        select(Category.category_name)
        .join(ProductCategory, ProductCategory.category_id == Category.category_id)
        .where(ProductCategory.product_id == report.product_id)
        .order_by(Category.category_level.desc(), Category.category_name)
    ).all()
    category = ", ".join(dict.fromkeys(name for name in category_names if name))

    claim_rows = session.scalars(
        select(ProductReportClaimORM)
        .where(ProductReportClaimORM.llm_product_report_id == report_id)
        .order_by(
            ProductReportClaimORM.sort_order, ProductReportClaimORM.report_claim_id
        )
    ).all()
    citation_rows = (
        session.scalars(
            select(ProductReportCitationORM)
            .where(
                ProductReportCitationORM.report_claim_id.in_(
                    [row.report_claim_id for row in claim_rows]
                )
            )
            .order_by(
                ProductReportCitationORM.report_claim_id,
                ProductReportCitationORM.sort_order,
                ProductReportCitationORM.report_citation_id,
            )
        ).all()
        if claim_rows
        else []
    )
    citations_by_claim: dict[int, list[ProductReportCitationORM]] = {}
    for citation in citation_rows:
        citations_by_claim.setdefault(citation.report_claim_id, []).append(citation)

    review_ids = {citation.source_review_id for citation in citation_rows}
    review_rows = (
        session.scalars(select(Review).where(Review.review_id.in_(review_ids))).all()
        if review_ids
        else []
    )
    reviews: dict[int | str, Mapping[str, Any]] = {
        int(review.review_id): {
            "product_id": review.product_id,
            "review_content": review.review_content,
        }
        for review in review_rows
    }

    claims = [
        {
            "claim_id": str(claim.report_claim_id),
            "text": claim.claim_text,
            "citations": [
                {
                    "source_review_id": int(citation.source_review_id),
                    "quote": citation.quote_text or "",
                }
                for citation in citations_by_claim.get(claim.report_claim_id, [])
            ],
        }
        for claim in claim_rows
    ]

    attribute_rows = session.scalars(
        select(ProductReportAttribute)
        .where(
            ProductReportAttribute.llm_product_report_id == report_id,
            ProductReportAttribute.product_id == report.product_id,
        )
        .order_by(
            ProductReportAttribute.analysis_category_id,
            ProductReportAttribute.display_name,
            ProductReportAttribute.llm_product_attribute_report_id,
        )
    ).all()
    attributes = [
        {
            "attribute_report_id": int(row.llm_product_attribute_report_id),
            "analysis_category_id": int(row.analysis_category_id),
            "display_name": row.display_name,
            "positive_summary": row.positive_summary,
            "negative_summary": row.negative_summary,
            "generated_at": row.generated_at.isoformat()
            if row.generated_at is not None
            else None,
        }
        for row in attribute_rows
    ]

    sentiment_label = func.lower(func.trim(SentimentAnalysis.sentiment_label))
    overall_row = session.execute(
        select(
            func.count(ReviewSentence.aspect_sentence_id),
            func.sum(case((sentiment_label.in_(POSITIVE_LABELS), 1), else_=0)),
            func.sum(case((sentiment_label.in_(NEGATIVE_LABELS), 1), else_=0)),
            func.sum(case((sentiment_label.in_(NEUTRAL_LABELS), 1), else_=0)),
        )
        .join(Review, Review.review_id == ReviewSentence.review_id)
        .outerjoin(
            SentimentAnalysis,
            SentimentAnalysis.aspect_sentence_id == ReviewSentence.aspect_sentence_id,
        )
        .where(Review.product_id == report.product_id)
    ).one()
    total_sentence_count = int(overall_row[0] or 0)
    overall_positive = int(overall_row[1] or 0)
    overall_negative = int(overall_row[2] or 0)
    overall_neutral = int(overall_row[3] or 0)

    aspect_rows = session.execute(
        select(
            ReviewSentence.analysis_category_id,
            ReviewSentence.model_attribute_name,
            AnalysisCategoryAttribute.display_name,
            func.count(ReviewSentence.aspect_sentence_id),
            func.sum(case((sentiment_label.in_(POSITIVE_LABELS), 1), else_=0)),
            func.sum(case((sentiment_label.in_(NEGATIVE_LABELS), 1), else_=0)),
            func.sum(case((sentiment_label.in_(NEUTRAL_LABELS), 1), else_=0)),
        )
        .join(Review, Review.review_id == ReviewSentence.review_id)
        .outerjoin(
            SentimentAnalysis,
            SentimentAnalysis.aspect_sentence_id == ReviewSentence.aspect_sentence_id,
        )
        .outerjoin(
            AnalysisCategoryAttribute,
            and_(
                AnalysisCategoryAttribute.analysis_category_id
                == ReviewSentence.analysis_category_id,
                AnalysisCategoryAttribute.model_attribute_name
                == ReviewSentence.model_attribute_name,
            ),
        )
        .where(Review.product_id == report.product_id)
        .group_by(
            ReviewSentence.analysis_category_id,
            ReviewSentence.model_attribute_name,
            AnalysisCategoryAttribute.display_name,
        )
        .order_by(
            ReviewSentence.analysis_category_id,
            ReviewSentence.model_attribute_name,
        )
    ).all()

    def ratio(count: int, total: int) -> float:
        return round((count / total) * 100, 1) if total else 0.0

    aspect_summary: dict[str, dict[str, int | float]] = {}
    for row in aspect_rows:
        total = int(row[3] or 0)
        positive = int(row[4] or 0)
        negative = int(row[5] or 0)
        neutral = int(row[6] or 0)
        name = row[2] or row[1] or f"category:{row[0]}"
        key = str(name)
        if key in aspect_summary:
            key = f"{row[0]}:{key}"
        aspect_summary[key] = {
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "positive_ratio": ratio(positive, total),
        }

    total_reviews = session.scalar(
        select(func.count(Review.review_id)).where(
            Review.product_id == report.product_id
        )
    )
    complaint_ids = [
        str(claim.report_claim_id)
        for claim in claim_rows
        if claim.claim_kind == "complaint"
    ]
    praise_ids = [
        str(claim.report_claim_id)
        for claim in claim_rows
        if claim.claim_kind == "praise"
    ]
    payload: dict[str, Any] = {
        "schema_version": 2,
        "report_id": int(report.llm_product_report_id),
        "product_id": int(report.product_id),
        "product_code": product.product_code,
        "product_name": product.product_name,
        "brand_name": brand_name,
        "category": category,
        "report_status": report.report_status or "abstained",
        "abstention_reason": report.abstention_reason,
        "total_reviews_analyzed": int(total_reviews or 0),
        "aspect_summary": aspect_summary,
        "statistics": {
            "total_sentence_count": total_sentence_count,
            "positive_count": overall_positive,
            "negative_count": overall_negative,
            "neutral_count": overall_neutral,
            "positive_ratio": ratio(overall_positive, total_sentence_count),
            "negative_ratio": ratio(overall_negative, total_sentence_count),
        },
        "attributes": attributes,
        "markdown_report": report.overall_summary or "",
        "created_at": report.generated_at.isoformat()
        if report.generated_at is not None
        else None,
        "claims": claims,
        "key_complaints": complaint_ids,
        "key_praises": praise_ids,
        "improvement_suggestions": [],
    }
    return project_report(payload, reviews=reviews)
