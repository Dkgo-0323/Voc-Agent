"""Fixed PostgreSQL aggregate queries for the controlled analytics tool."""

from collections.abc import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.settings import settings
from backend.app.db.models import AspectMention, Sku
from backend.app.db.repositories.schemas import (
    AnalyticsComparisonRow,
    AnalyticsCountRow,
    AnalyticsDistributionRow,
    AnalyticsTrendRow,
    SkuMetadata,
)


class AnalyticsRepository:
    """Repository exposing approved aggregates only; it cannot execute caller SQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _apply_scope(
        statement,
        *,
        sku_codes: Sequence[str],
        week_range: tuple[int, int] | None,
        aspect_label: str | None,
        sentiment: str | None,
        quality_threshold: float,
    ):
        statement = statement.join(
            Sku, Sku.sku_code == AspectMention.sku_code
        ).where(
            Sku.dashboard_enabled.is_(True),
            AspectMention.quality_score >= quality_threshold,
        )
        if sku_codes:
            statement = statement.where(AspectMention.sku_code.in_(sku_codes))
        if week_range is not None:
            statement = statement.where(
                AspectMention.week_id >= week_range[0],
                AspectMention.week_id <= week_range[1],
            )
        if aspect_label is not None:
            statement = statement.where(AspectMention.aspect_label == aspect_label)
        if sentiment is not None:
            statement = statement.where(AspectMention.sentiment == sentiment)
        return statement

    async def get_enabled_skus(self) -> list[SkuMetadata]:
        result = await self._session.execute(
            select(Sku).where(Sku.dashboard_enabled.is_(True)).order_by(Sku.sku_code)
        )
        return [SkuMetadata.model_validate(sku) for sku in result.scalars()]

    async def get_counts(
        self,
        *,
        sku_codes: Sequence[str],
        week_range: tuple[int, int] | None = None,
        aspect_label: str | None = None,
        sentiment: str | None = None,
        quality_threshold: float = settings.aspect_quality_threshold,
    ) -> list[AnalyticsCountRow]:
        statement = select(
            AspectMention.sku_code,
            func.count(func.distinct(AspectMention.document_id)).label("review_count"),
            func.count(AspectMention.id).label("mention_count"),
        )
        statement = self._apply_scope(
            statement,
            sku_codes=sku_codes,
            week_range=week_range,
            aspect_label=aspect_label,
            sentiment=sentiment,
            quality_threshold=quality_threshold,
        )
        rows = await self._session.execute(
            statement.group_by(AspectMention.sku_code).order_by(AspectMention.sku_code)
        )
        return [AnalyticsCountRow.model_validate(row._mapping) for row in rows]

    async def get_sentiment_distribution(
        self,
        *,
        sku_codes: Sequence[str],
        week_range: tuple[int, int] | None = None,
        aspect_label: str | None = None,
        sentiment: str | None = None,
        quality_threshold: float = settings.aspect_quality_threshold,
    ) -> list[AnalyticsDistributionRow]:
        statement = select(
            AspectMention.sentiment.label("label"),
            func.count(AspectMention.id).label("mention_count"),
        )
        statement = self._apply_scope(
            statement,
            sku_codes=sku_codes,
            week_range=week_range,
            aspect_label=aspect_label,
            sentiment=sentiment,
            quality_threshold=quality_threshold,
        )
        rows = await self._session.execute(
            statement.group_by(AspectMention.sentiment).order_by(AspectMention.sentiment)
        )
        return [AnalyticsDistributionRow.model_validate(row._mapping) for row in rows]

    async def get_aspect_distribution(
        self,
        *,
        sku_codes: Sequence[str],
        week_range: tuple[int, int] | None = None,
        aspect_label: str | None = None,
        sentiment: str | None = None,
        limit: int = 10,
        quality_threshold: float = settings.aspect_quality_threshold,
    ) -> list[AnalyticsDistributionRow]:
        statement = select(
            AspectMention.aspect_label.label("label"),
            func.count(AspectMention.id).label("mention_count"),
            func.sum(case((AspectMention.sentiment == "positive", 1), else_=0)).label(
                "positive_count"
            ),
            func.sum(case((AspectMention.sentiment == "negative", 1), else_=0)).label(
                "negative_count"
            ),
            func.sum(case((AspectMention.sentiment == "neutral", 1), else_=0)).label(
                "neutral_count"
            ),
        )
        statement = self._apply_scope(
            statement,
            sku_codes=sku_codes,
            week_range=week_range,
            aspect_label=aspect_label,
            sentiment=sentiment,
            quality_threshold=quality_threshold,
        )
        rows = await self._session.execute(
            statement.group_by(AspectMention.aspect_label)
            .order_by(func.count(AspectMention.id).desc(), AspectMention.aspect_label)
            .limit(limit)
        )
        return [AnalyticsDistributionRow.model_validate(row._mapping) for row in rows]

    async def get_trend(
        self,
        *,
        sku_codes: Sequence[str],
        week_range: tuple[int, int] | None = None,
        aspect_label: str | None = None,
        sentiment: str | None = None,
        quality_threshold: float = settings.aspect_quality_threshold,
    ) -> list[AnalyticsTrendRow]:
        statement = select(
            AspectMention.week_id,
            func.count(func.distinct(AspectMention.document_id)).label("review_count"),
            func.count(AspectMention.id).label("mention_count"),
            func.sum(case((AspectMention.sentiment == "positive", 1), else_=0)).label(
                "positive_count"
            ),
            func.sum(case((AspectMention.sentiment == "negative", 1), else_=0)).label(
                "negative_count"
            ),
            func.sum(case((AspectMention.sentiment == "neutral", 1), else_=0)).label(
                "neutral_count"
            ),
        )
        statement = self._apply_scope(
            statement,
            sku_codes=sku_codes,
            week_range=week_range,
            aspect_label=aspect_label,
            sentiment=sentiment,
            quality_threshold=quality_threshold,
        )
        rows = await self._session.execute(
            statement.group_by(AspectMention.week_id).order_by(AspectMention.week_id)
        )
        return [AnalyticsTrendRow.model_validate(row._mapping) for row in rows]

    async def get_comparison(
        self,
        *,
        sku_codes: Sequence[str],
        week_range: tuple[int, int] | None = None,
        aspect_label: str | None = None,
        sentiment: str | None = None,
        quality_threshold: float = settings.aspect_quality_threshold,
    ) -> list[AnalyticsComparisonRow]:
        statement = select(
            AspectMention.sku_code,
            Sku.capacity_tier,
            func.count(func.distinct(AspectMention.document_id)).label("review_count"),
            func.count(AspectMention.id).label("mention_count"),
            func.sum(case((AspectMention.sentiment == "positive", 1), else_=0)).label(
                "positive_count"
            ),
            func.sum(case((AspectMention.sentiment == "negative", 1), else_=0)).label(
                "negative_count"
            ),
            func.sum(case((AspectMention.sentiment == "neutral", 1), else_=0)).label(
                "neutral_count"
            ),
        )
        statement = self._apply_scope(
            statement,
            sku_codes=sku_codes,
            week_range=week_range,
            aspect_label=aspect_label,
            sentiment=sentiment,
            quality_threshold=quality_threshold,
        )
        rows = await self._session.execute(
            statement.group_by(AspectMention.sku_code, Sku.capacity_tier).order_by(
                AspectMention.sku_code
            )
        )
        return [AnalyticsComparisonRow.model_validate(row._mapping) for row in rows]
