"""
所有 ORM 模型定义（7张表）
对应文档 Section 4.2
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────
# skus
# ──────────────────────────────────────────────
class Sku(Base):
    __tablename__ = "skus"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    sku_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    category: Mapped[str] = mapped_column(
        Text, default="portable-power-station", nullable=False
    )
    capacity_wh: Mapped[int | None] = mapped_column(Integer)
    capacity_tier: Mapped[str | None] = mapped_column(Text)  # 'entry' | 'mid'
    is_competitor: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dashboard_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now()
    )

    # relationships
    documents: Mapped[list["Document"]] = relationship(back_populates="sku")
    weekly_reports: Mapped[list["WeeklyReport"]] = relationship(back_populates="sku")


# ──────────────────────────────────────────────
# documents
# ──────────────────────────────────────────────
class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_documents_platform_ext"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id"), nullable=False
    )
    platform: Mapped[str] = mapped_column(Text, nullable=False)  # 'reddit' | 'amazon'
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    author_hash: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column()
    week_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now()
    )
    processing_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="raw", server_default="raw", index=True
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column()

    # relationships
    sku: Mapped["Sku"] = relationship(back_populates="documents")
    aspect_mentions: Mapped[list["AspectMention"]] = relationship(
        back_populates="document"
    )


# ──────────────────────────────────────────────
# aspect_mentions
# ──────────────────────────────────────────────
class AspectMention(Base):
    __tablename__ = "aspect_mentions"
    __table_args__ = (
        Index("ix_aspect_mentions_sku_code", "sku_code"),
        Index("ix_aspect_mentions_aspect_label", "aspect_label"),
        Index("ix_aspect_mentions_week_id", "week_id"),
        Index("ix_aspect_mentions_quality_score", "quality_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    sku_code: Mapped[str] = mapped_column(Text, nullable=False)
    aspect_label: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    mention_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_window: Mapped[str | None] = mapped_column(Text)
    quality_score: Mapped[float | None] = mapped_column(Float)
    embed_text: Mapped[str | None] = mapped_column(Text)
    week_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now()
    )

    # relationships
    document: Mapped["Document"] = relationship(back_populates="aspect_mentions")


# ──────────────────────────────────────────────
# weekly_reports
# ──────────────────────────────────────────────
class WeeklyReport(Base):
    __tablename__ = "weekly_reports"
    __table_args__ = (
        UniqueConstraint("sku_id", "week_id", name="uq_weekly_reports_sku_week"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id"), nullable=False
    )
    week_id: Mapped[int] = mapped_column(Integer, nullable=False)
    report_md: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now()
    )

    # relationships
    sku: Mapped["Sku"] = relationship(back_populates="weekly_reports")
    weekly_topics: Mapped[list["WeeklyTopic"]] = relationship(
        back_populates="weekly_report"
    )


# ──────────────────────────────────────────────
# weekly_topics
# ──────────────────────────────────────────────
class WeeklyTopic(Base):
    __tablename__ = "weekly_topics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    weekly_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("weekly_reports.id"), nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id"), nullable=False
    )
    week_id: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_label: Mapped[str] = mapped_column(Text, nullable=False)
    topic_summary: Mapped[str | None] = mapped_column(Text)
    mention_count: Mapped[int | None] = mapped_column(Integer)
    avg_sentiment: Mapped[float | None] = mapped_column(Float)
    top_aspects: Mapped[dict | None] = mapped_column(JSONB)

    # relationships
    weekly_report: Mapped["WeeklyReport"] = relationship(back_populates="weekly_topics")


# ──────────────────────────────────────────────
# chat_sessions
# ──────────────────────────────────────────────
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)  # nullable，预留多用户
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now(), onupdate=utcnow
    )

    # relationships
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session")


# ──────────────────────────────────────────────
# chat_messages
# ──────────────────────────────────────────────
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB)
    tool_results: Mapped[dict | None] = mapped_column(JSONB)
    cited_ids: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        default=utcnow, server_default=func.now()
    )

    # relationships
    session: Mapped["ChatSession"] = relationship(back_populates="messages")
