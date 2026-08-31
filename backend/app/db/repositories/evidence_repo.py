"""PostgreSQL hydration for Milvus aspect-mention search results."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.settings import settings
from backend.app.db.models import AspectMention, Document, Sku
from backend.app.db.repositories.schemas import RetrievedEvidenceRow, SkuMetadata


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_enabled_skus(self) -> list[SkuMetadata]:
        result = await self._session.execute(
            select(Sku).where(Sku.dashboard_enabled.is_(True)).order_by(Sku.sku_code)
        )
        return [SkuMetadata.model_validate(sku) for sku in result.scalars()]

    async def hydrate_mentions(
        self,
        mention_ids: Sequence[UUID],
        *,
        quality_threshold: float = settings.aspect_quality_threshold,
    ) -> list[RetrievedEvidenceRow]:
        if not mention_ids:
            return []
        statement = (
            select(
                AspectMention.id.label("mention_id"),
                AspectMention.document_id,
                AspectMention.sku_code,
                AspectMention.aspect_label,
                AspectMention.sentiment,
                AspectMention.mention_text,
                AspectMention.context_window,
                AspectMention.quality_score,
                AspectMention.week_id,
                Document.platform,
                Document.published_at,
                Document.source_url,
                Document.title,
                Document.rating,
                Document.body.label("review_text"),
            )
            .join(Document, Document.id == AspectMention.document_id)
            .join(Sku, Sku.id == Document.sku_id)
            .where(
                AspectMention.id.in_(mention_ids),
                AspectMention.quality_score >= quality_threshold,
                Sku.dashboard_enabled.is_(True),
                Sku.sku_code == AspectMention.sku_code,
            )
        )
        rows = await self._session.execute(statement)
        return [RetrievedEvidenceRow.model_validate(row._mapping) for row in rows]
