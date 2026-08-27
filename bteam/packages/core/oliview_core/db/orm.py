from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(30), unique=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.brand_id"))
    product_name: Mapped[str] = mapped_column(String(300), default="")
    product_image_url: Mapped[str | None] = mapped_column(String(500))
    first_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    option_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    llm_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Brand(Base):
    __tablename__ = "brands"
    brand_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_name: Mapped[str] = mapped_column(String(255), default="")


class Category(Base):
    __tablename__ = "categories"
    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_category_id: Mapped[int | None] = mapped_column(Integer)
    category_name: Mapped[str] = mapped_column(String(100), default="")
    category_level: Mapped[int] = mapped_column(Integer, default=0)


class ProductCategory(Base):
    __tablename__ = "product_categories"
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.category_id"), primary_key=True
    )


class AnalysisCategoryAttribute(Base):
    __tablename__ = "analysis_category_attributes"
    analysis_category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_attribute_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class Review(Base):
    __tablename__ = "reviews"
    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_code: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"), index=True
    )
    product_option_id: Mapped[int | None] = mapped_column(Integer)
    review_content: Mapped[str] = mapped_column(Text)
    review_score: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    review_date: Mapped[date] = mapped_column(
        Date, default=date.today, nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    preprocessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aspect_split_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sentiment_analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    vector_indexed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )


class ReviewPreprocessing(Base):
    __tablename__ = "review_preprocessing"
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.review_id", ondelete="CASCADE"), primary_key=True
    )
    cleaned_content: Mapped[str] = mapped_column(Text)


class ReviewSentence(Base):
    __tablename__ = "review_aspect_sentences"
    aspect_sentence_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.review_id"), index=True)
    analysis_category_id: Mapped[int | None] = mapped_column(Integer)
    model_attribute_name: Mapped[str | None] = mapped_column(String(100))
    separated_sentence: Mapped[str] = mapped_column(Text)
    sequence_no: Mapped[int | None] = mapped_column(Integer)
    sentence_start: Mapped[int | None] = mapped_column(Integer)
    sentence_end: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column()
    embedding_vector: Mapped[list[float] | None] = mapped_column(JSON)
    speaker: Mapped[str | None] = mapped_column(String(255))
    product_name: Mapped[str | None] = mapped_column(String(255))
    brand_name: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(100))
    sentiment_label: Mapped[str | None] = mapped_column(String(20))
    display_name: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_category_id", "model_attribute_name"],
            [
                "analysis_category_attributes.analysis_category_id",
                "analysis_category_attributes.model_attribute_name",
            ],
        ),
    )


class SentimentAnalysis(Base):
    __tablename__ = "aspect_sentiment_results"
    aspect_sentence_id: Mapped[int] = mapped_column(
        ForeignKey("review_aspect_sentences.aspect_sentence_id"), primary_key=True
    )
    sentiment_label: Mapped[str] = mapped_column(String(32))
    confidence_score: Mapped[float | None]


class ProductReport(Base):
    __tablename__ = "llm_product_reports"
    llm_product_report_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"), index=True
    )
    report_status: Mapped[str] = mapped_column(
        String(32), default="abstained", server_default="abstained"
    )
    abstention_reason: Mapped[str | None] = mapped_column(String(64))
    keep_summary: Mapped[str | None] = mapped_column(Text)
    improvement_summary: Mapped[str | None] = mapped_column(Text)
    overall_summary: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductReportAttribute(Base):
    __tablename__ = "llm_product_attribute_reports"
    llm_product_attribute_report_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    llm_product_report_id: Mapped[int] = mapped_column(
        ForeignKey("llm_product_reports.llm_product_report_id")
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    analysis_category_id: Mapped[int] = mapped_column(Integer)
    display_name: Mapped[str] = mapped_column(String(100))
    positive_summary: Mapped[str | None] = mapped_column(Text)
    negative_summary: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductReportClaimORM(Base):
    __tablename__ = "llm_product_report_claims"
    report_claim_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    llm_product_report_id: Mapped[int] = mapped_column(
        ForeignKey("llm_product_reports.llm_product_report_id")
    )
    claim_key: Mapped[str] = mapped_column(String(128))
    claim_kind: Mapped[str] = mapped_column(String(32))
    claim_text: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint(
            "llm_product_report_id", "claim_key", name="uq_report_claim_key"
        ),
    )


class ProductReportCitationORM(Base):
    __tablename__ = "llm_product_report_citations"
    report_citation_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    report_claim_id: Mapped[int] = mapped_column(
        ForeignKey("llm_product_report_claims.report_claim_id")
    )
    source_review_id: Mapped[int] = mapped_column(ForeignKey("reviews.review_id"))
    quote_text: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint(
            "report_claim_id",
            "source_review_id",
            "sort_order",
            name="uq_claim_review_quote",
        ),
    )


class PipelineRunHistoryORM(Base):
    __tablename__ = "pipeline_run_history"
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[str] = mapped_column(String(128))
    step_name: Mapped[str] = mapped_column(String(64))
    scope_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    checkpoint_payload: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("run_id", "step_name", "scope_key", name="uq_run_history"),
    )


class PipelineActiveLeaseORM(Base):
    __tablename__ = "pipeline_active_lease"
    step_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_token: Mapped[str] = mapped_column(String(128))
    run_id: Mapped[str] = mapped_column(String(128))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def create_all(engine: object) -> None:
    Base.metadata.create_all(engine)  # type: ignore[arg-type]
