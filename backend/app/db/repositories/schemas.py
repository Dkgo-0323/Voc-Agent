"""Repository input/output schemas.

Repositories deliberately return these schemas instead of leaking SQLAlchemy
models to the pipeline and API layers.
"""

from datetime import datetime
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
