"""Data access for extracted aspect mentions and dashboard aggregations."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import case, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AspectMention
from backend.app.db.repositories.schemas import (
    AspectMentionCreate,
    SkuTrend,
    TopAspect,
)

_SENTIMENT_VALUE = case(
    (AspectMention.sentiment == "positive", 1.0),
    (AspectMention.sentiment == "negative", -1.0),
    else_=0.0,
)


class AspectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_insert(self, mentions: Sequence[AspectMentionCreate]) -> list[UUID]:
        if not mentions:
            return []
        result = await self._session.execute(
            insert(AspectMention)
            .values([mention.model_dump() for mention in mentions])
            .returning(AspectMention.id)
        )
        return list(result.scalars())

    async def get_sentiment_breakdown(
        self, week_id: int, sku_code: str | None = None
    ) -> dict[str, int]:
        statement = select(
            AspectMention.sentiment, func.count(AspectMention.id).label("count")
        ).where(AspectMention.week_id == week_id)
        if sku_code is not None:
            statement = statement.where(AspectMention.sku_code == sku_code)
        result = await self._session.execute(statement.group_by(AspectMention.sentiment))
        breakdown = {"positive": 0, "negative": 0, "neutral": 0}
        breakdown.update({sentiment: count for sentiment, count in result})
        return breakdown

    async def get_top_aspects(
        self, week_id: int, sku_code: str | None = None, limit: int = 10
    ) -> list[TopAspect]:
        if limit <= 0:
            return []
        statement = (
            select(
                AspectMention.aspect_label,
                func.count(AspectMention.id).label("count"),
                func.avg(_SENTIMENT_VALUE).label("avg_sentiment_score"),
            )
            .where(AspectMention.week_id == week_id)
            .group_by(AspectMention.aspect_label)
            .order_by(func.count(AspectMention.id).desc(), AspectMention.aspect_label)
            .limit(limit)
        )
        if sku_code is not None:
            statement = statement.where(AspectMention.sku_code == sku_code)
        rows = await self._session.execute(statement)
        return [
            TopAspect(
                aspect_label=row.aspect_label,
                count=row.count,
                avg_sentiment_score=float(row.avg_sentiment_score),
            )
            for row in rows
        ]

    async def get_sku_trends(
        self, sku_code: str, week_ids: Sequence[int]
    ) -> list[SkuTrend]:
        if not week_ids:
            return []
        statement = (
            select(
                AspectMention.week_id,
                AspectMention.aspect_label,
                func.sum(case((AspectMention.sentiment == "positive", 1), else_=0)).label(
                    "positive_count"
                ),
                func.sum(case((AspectMention.sentiment == "negative", 1), else_=0)).label(
                    "negative_count"
                ),
            )
            .where(
                AspectMention.sku_code == sku_code,
                AspectMention.week_id.in_(week_ids),
            )
            .group_by(AspectMention.week_id, AspectMention.aspect_label)
            .order_by(AspectMention.week_id, AspectMention.aspect_label)
        )
        rows = await self._session.execute(statement)
        return [SkuTrend.model_validate(row._mapping) for row in rows]
