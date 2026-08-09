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


class TopAspect(BaseModel):
    aspect_label: str
    count: int
    avg_sentiment_score: float


class SkuTrend(BaseModel):
    week_id: int
    aspect_label: str
    positive_count: int
    negative_count: int
