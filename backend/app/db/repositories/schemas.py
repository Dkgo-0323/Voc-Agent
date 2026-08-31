"""Repository input/output schemas.

Repositories deliberately return these schemas instead of leaking SQLAlchemy
models to the pipeline and API layers.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku_id: UUID
    sku_code: str
    sku_name: str
    platform: str
    external_id: str
    title: str | None
    body: str
    rating: int | None
    author_hash: str | None
    source_url: str | None
    published_at: datetime | None
    week_id: int
    ingested_at: datetime
    processing_status: str
    processing_error: str | None
    processed_at: datetime | None


class AspectMentionCreate(BaseModel):
    document_id: UUID
    sku_code: str = Field(min_length=1)
    week_id: int
    aspect_label: str = Field(min_length=1)
    sentiment: str = Field(pattern="^(positive|negative|neutral)$")
    sentiment_score: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    mention_text: str = Field(min_length=1)
    context_window: str | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    embed_text: str | None = None


class AspectMentionRead(AspectMentionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class TopAspect(BaseModel):
    aspect_label: str
    count: int
    positive_count: int
    avg_sentiment_score: float


class SkuTrend(BaseModel):
    week_id: int
    aspect_label: str
    positive_count: int
    negative_count: int
    neutral_count: int
    avg_quality_score: float


class WeekAggregation(BaseModel):
    week_id: int
    doc_count: int
    mention_count: int
    skus_covered: list[str]


class SkuRanking(BaseModel):
    sku_code: str
    sku_name: str
    mention_count: int
    positive_count: int
    negative_count: int


class SkuMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku_code: str
    brand: str
    model: str
    capacity_wh: int | None
    capacity_tier: str | None
    is_competitor: bool
    dashboard_enabled: bool

    @property
    def sku_name(self) -> str:
        return f"{self.brand} {self.model}"


class WeeklyReportRow(BaseModel):
    report_id: UUID
    sku_code: str
    week_id: int
    report_md: str | None
    summary: str | None
    generated_at: datetime


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_by: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    role: str
    content: str
    tool_calls: dict[str, Any] | None
    tool_results: dict[str, Any] | None
    cited_ids: dict[str, Any] | None
    created_at: datetime


class PersistedTurnRow(BaseModel):
    user_message_id: UUID
    assistant_message_id: UUID


class AnalyticsCountRow(BaseModel):
    sku_code: str
    review_count: int
    mention_count: int


class AnalyticsDistributionRow(BaseModel):
    label: str
    mention_count: int
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0


class AnalyticsTrendRow(BaseModel):
    week_id: int
    review_count: int
    mention_count: int
    positive_count: int
    negative_count: int
    neutral_count: int


class AnalyticsComparisonRow(BaseModel):
    sku_code: str
    capacity_tier: str | None
    review_count: int
    mention_count: int
    positive_count: int
    negative_count: int
    neutral_count: int


class RetrievedEvidenceRow(BaseModel):
    mention_id: UUID
    document_id: UUID
    sku_code: str
    aspect_label: str
    sentiment: str
    mention_text: str
    context_window: str | None
    quality_score: float
    week_id: int
    platform: str
    published_at: datetime | None
    source_url: str | None
    title: str | None
    rating: int | None
    review_text: str
