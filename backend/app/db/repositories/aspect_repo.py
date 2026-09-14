"""Data access for extracted aspect mentions and dashboard aggregations."""

from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import case, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.settings import settings
from backend.app.db.models import AspectMention, Document, Sku
from backend.app.db.repositories.schemas import (
    AspectMentionCreate,
    AspectMentionRead,
    RetrievedEvidenceRow,
    SkuMetadata,
    SkuRanking,
    SkuTrend,
    TopAspect,
    WeekAggregation,
)

_SENTIMENT_VALUE = case(
    (AspectMention.sentiment == "positive", 1.0),
    (AspectMention.sentiment == "negative", -1.0),
    else_=0.0,
)


class AspectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _with_quality_threshold(statement, quality_threshold: float | None):
        if quality_threshold is None:
            return statement
        return statement.where(AspectMention.quality_score >= quality_threshold)

    async def bulk_insert(self, mentions: Sequence[AspectMentionCreate]) -> list[UUID]:
        if not mentions:
            return []
        result = await self._session.execute(
            insert(AspectMention)
            .values([mention.model_dump() for mention in mentions])
            .returning(AspectMention.id)
        )
        return list(result.scalars())

    async def fetch_by_document_ids(
        self, document_ids: Sequence[UUID]
    ) -> list[AspectMentionRead]:
        """Return the persisted mentions needed by the embedding stage."""
        if not document_ids:
            return []
        result = await self._session.execute(
            select(AspectMention)
            .where(AspectMention.document_id.in_(document_ids))
            .order_by(AspectMention.document_id, AspectMention.id)
        )
        return [
            AspectMentionRead.model_validate(mention) for mention in result.scalars()
        ]

    async def bulk_update_embed_text(self, embed_text_by_id: Mapping[UUID, str]) -> int:
        """Persist the exact text used to generate each Milvus vector."""
        updated = 0
        for mention_id, embed_text in embed_text_by_id.items():
            result = await self._session.execute(
                update(AspectMention)
                .where(AspectMention.id == mention_id)
                .values(embed_text=embed_text)
            )
            updated += result.rowcount or 0
        return updated

    async def get_sentiment_breakdown(
        self,
        week_id: int,
        sku_code: str | None = None,
        *,
        include_disabled: bool = False,
        quality_threshold: float | None = settings.aspect_quality_threshold,
    ) -> dict[str, int]:
        statement = select(
            AspectMention.sentiment, func.count(AspectMention.id).label("count")
        ).where(AspectMention.week_id == week_id)
        statement = self._with_quality_threshold(statement, quality_threshold)
        if sku_code is not None:
            statement = statement.where(AspectMention.sku_code == sku_code)
        if not include_disabled:
            statement = statement.join(
                Sku, Sku.sku_code == AspectMention.sku_code
            ).where(Sku.dashboard_enabled.is_(True))
        result = await self._session.execute(
            statement.group_by(AspectMention.sentiment)
        )
        breakdown = {"positive": 0, "negative": 0, "neutral": 0}
        breakdown.update({sentiment: count for sentiment, count in result})
        return breakdown

    async def get_top_aspects(
        self,
        week_id: int,
        sku_code: str | None = None,
        limit: int = 10,
        *,
        include_disabled: bool = False,
        quality_threshold: float | None = settings.aspect_quality_threshold,
    ) -> list[TopAspect]:
        if limit <= 0:
            return []
        statement = (
            select(
                AspectMention.aspect_label,
                func.count(AspectMention.id).label("count"),
                func.sum(
                    case((AspectMention.sentiment == "positive", 1), else_=0)
                ).label("positive_count"),
                func.avg(_SENTIMENT_VALUE).label("avg_sentiment_score"),
            )
            .where(AspectMention.week_id == week_id)
            .group_by(AspectMention.aspect_label)
            .order_by(func.count(AspectMention.id).desc(), AspectMention.aspect_label)
            .limit(limit)
        )
        statement = self._with_quality_threshold(statement, quality_threshold)
        if sku_code is not None:
            statement = statement.where(AspectMention.sku_code == sku_code)
        if not include_disabled:
            statement = statement.join(
                Sku, Sku.sku_code == AspectMention.sku_code
            ).where(Sku.dashboard_enabled.is_(True))
        rows = await self._session.execute(statement)
        return [
            TopAspect(
                aspect_label=row.aspect_label,
                count=row.count,
                positive_count=row.positive_count,
                avg_sentiment_score=float(row.avg_sentiment_score),
            )
            for row in rows
        ]

    async def get_sku_trends(
        self,
        sku_code: str,
        week_ids: Sequence[int],
        *,
        include_disabled: bool = False,
        quality_threshold: float | None = settings.aspect_quality_threshold,
    ) -> list[SkuTrend]:
        if not week_ids:
            return []
        statement = (
            select(
                AspectMention.week_id,
                AspectMention.aspect_label,
                func.sum(
                    case((AspectMention.sentiment == "positive", 1), else_=0)
                ).label("positive_count"),
                func.sum(
                    case((AspectMention.sentiment == "negative", 1), else_=0)
                ).label("negative_count"),
                func.sum(
                    case((AspectMention.sentiment == "neutral", 1), else_=0)
                ).label("neutral_count"),
                func.coalesce(func.avg(AspectMention.quality_score), 0.0).label(
                    "avg_quality_score"
                ),
            )
            .where(
                AspectMention.sku_code == sku_code,
                AspectMention.week_id.in_(week_ids),
            )
            .group_by(AspectMention.week_id, AspectMention.aspect_label)
            .order_by(AspectMention.week_id, AspectMention.aspect_label)
        )
        statement = self._with_quality_threshold(statement, quality_threshold)
        if not include_disabled:
            statement = statement.join(
                Sku, Sku.sku_code == AspectMention.sku_code
            ).where(Sku.dashboard_enabled.is_(True))
        rows = await self._session.execute(statement)
        return [SkuTrend.model_validate(row._mapping) for row in rows]

    async def get_week_aggregations(
        self,
        *,
        include_disabled: bool = False,
        quality_threshold: float | None = settings.aspect_quality_threshold,
    ) -> list[WeekAggregation]:
        statement = (
            select(
                AspectMention.week_id,
                func.count(func.distinct(AspectMention.document_id)).label("doc_count"),
                func.count(AspectMention.id).label("mention_count"),
                func.array_agg(func.distinct(AspectMention.sku_code)).label(
                    "skus_covered"
                ),
            )
            .group_by(AspectMention.week_id)
            .order_by(AspectMention.week_id.desc())
        )
        statement = self._with_quality_threshold(statement, quality_threshold)
        if not include_disabled:
            statement = statement.join(
                Sku, Sku.sku_code == AspectMention.sku_code
            ).where(Sku.dashboard_enabled.is_(True))
        rows = await self._session.execute(statement)
        return [WeekAggregation.model_validate(row._mapping) for row in rows]

    async def get_week_ids(
        self,
        *,
        limit: int | None = None,
        sku_code: str | None = None,
        include_disabled: bool = False,
        quality_threshold: float | None = settings.aspect_quality_threshold,
    ) -> list[int]:
        statement = select(AspectMention.week_id).distinct()
        statement = self._with_quality_threshold(statement, quality_threshold)
        if sku_code is not None:
            statement = statement.where(AspectMention.sku_code == sku_code)
        if not include_disabled:
            statement = statement.join(
                Sku, Sku.sku_code == AspectMention.sku_code
            ).where(Sku.dashboard_enabled.is_(True))
        statement = statement.order_by(AspectMention.week_id.desc())
        if limit is not None:
            statement = statement.limit(limit)
        result = await self._session.execute(statement)
        return list(result.scalars())

    async def get_sku_rankings(
        self,
        week_id: int,
        *,
        include_disabled: bool = False,
        quality_threshold: float | None = settings.aspect_quality_threshold,
    ) -> list[SkuRanking]:
        statement = (
            select(
                AspectMention.sku_code,
                (Sku.brand + " " + Sku.model).label("sku_name"),
                func.count(AspectMention.id).label("mention_count"),
                func.sum(
                    case((AspectMention.sentiment == "positive", 1), else_=0)
                ).label("positive_count"),
                func.sum(
                    case((AspectMention.sentiment == "negative", 1), else_=0)
                ).label("negative_count"),
            )
            .join(Sku, Sku.sku_code == AspectMention.sku_code)
            .where(AspectMention.week_id == week_id)
            .group_by(AspectMention.sku_code, Sku.brand, Sku.model)
            .order_by(func.count(AspectMention.id).desc(), AspectMention.sku_code)
        )
        statement = self._with_quality_threshold(statement, quality_threshold)
        if not include_disabled:
            statement = statement.where(Sku.dashboard_enabled.is_(True))
        rows = await self._session.execute(statement)
        return [SkuRanking.model_validate(row._mapping) for row in rows]

    async def get_enabled_skus(self) -> list[SkuMetadata]:
        result = await self._session.execute(
            select(Sku).where(Sku.dashboard_enabled.is_(True)).order_by(Sku.sku_code)
        )
        return [SkuMetadata.model_validate(sku) for sku in result.scalars()]

    async def get_sku_week_summary(
        self,
        *,
        sku_code: str,
        week_id: int,
        quality_threshold: float | None = settings.aspect_quality_threshold,
    ) -> tuple[int, int]:
        """Return quality-qualified review and mention counts for one SKU/week."""
        statement = (
            select(
                func.count(func.distinct(AspectMention.document_id)).label(
                    "review_count"
                ),
                func.count(AspectMention.id).label("mention_count"),
            )
            .join(Sku, Sku.sku_code == AspectMention.sku_code)
            .where(
                AspectMention.sku_code == sku_code,
                AspectMention.week_id == week_id,
                Sku.dashboard_enabled.is_(True),
            )
        )
        statement = self._with_quality_threshold(statement, quality_threshold)
        row = (await self._session.execute(statement)).one()
        return int(row.review_count or 0), int(row.mention_count or 0)

    async def get_sku_evidence(
        self,
        *,
        sku_code: str,
        week_id: int,
        sentiment: str,
        limit: int,
        quality_threshold: float | None = settings.aspect_quality_threshold,
    ) -> list[RetrievedEvidenceRow]:
        """Return provenance-complete evidence in a stable display order.

        Quality score descending, then newest persisted mention, then mention ID
        makes repeated requests deterministic when quality scores tie.
        """
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
            .join(Sku, Sku.sku_code == AspectMention.sku_code)
            .where(
                AspectMention.sku_code == sku_code,
                AspectMention.week_id == week_id,
                AspectMention.sentiment == sentiment,
                Sku.dashboard_enabled.is_(True),
            )
            .order_by(
                AspectMention.quality_score.desc(),
                AspectMention.created_at.desc(),
                AspectMention.id,
            )
            .limit(limit)
        )
        statement = self._with_quality_threshold(statement, quality_threshold)
        rows = await self._session.execute(statement)
        return [RetrievedEvidenceRow.model_validate(row._mapping) for row in rows]

    async def validate_locked_skus(self, locked_sku_codes: set[str]) -> None:
        result = await self._session.execute(
            select(Sku.sku_code, Sku.dashboard_enabled).where(
                Sku.sku_code.in_(locked_sku_codes)
            )
        )
        states = {row[0]: row[1] for row in result}
        missing = sorted(locked_sku_codes - states.keys())
        disabled = sorted(code for code, enabled in states.items() if not enabled)
        if missing or disabled:
            raise RuntimeError(
                "Locked SKU consistency check failed: "
                f"missing={missing}, disabled={disabled}"
            )
