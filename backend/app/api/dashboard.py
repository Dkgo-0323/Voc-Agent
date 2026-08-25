"""Dashboard endpoints backed by PostgreSQL aggregate queries."""

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.db.repositories.aspect_repo import AspectRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Dashboard"])


class DashboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WeekResponse(DashboardResponse):
    week_id: int
    week_start: date
    week_end: date
    doc_count: int = Field(ge=0)
    mention_count: int = Field(ge=0)
    skus_covered: list[str]


class SentimentBreakdownResponse(DashboardResponse):
    positive: int = Field(ge=0)
    negative: int = Field(ge=0)
    neutral: int = Field(ge=0)


class OverviewSummaryResponse(DashboardResponse):
    total_mentions: int = Field(ge=0)
    sentiment_breakdown: SentimentBreakdownResponse


class TopAspectResponse(DashboardResponse):
    aspect_label: str
    mention_count: int = Field(ge=0)
    positive_rate: float = Field(ge=0, le=1)


class SkuRankingResponse(DashboardResponse):
    sku_code: str
    sku_name: str
    mention_count: int = Field(ge=0)
    sentiment_score: float = Field(ge=-1, le=1)


class OverviewResponse(DashboardResponse):
    week_id: int
    summary: OverviewSummaryResponse
    top_aspects: list[TopAspectResponse]
    sku_rankings: list[SkuRankingResponse]


class TrendPointResponse(DashboardResponse):
    week_id: int
    aspect_label: str
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    avg_quality_score: float = Field(ge=0, le=1)


class SkuTrendsResponse(DashboardResponse):
    sku_code: str
    sku_name: str
    capacity_tier: str
    trends: list[TrendPointResponse]


def get_aspect_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AspectRepository:
    return AspectRepository(db)


RepositoryDependency = Annotated[AspectRepository, Depends(get_aspect_repository)]


def _week_dates(week_id: int) -> tuple[date, date]:
    year, week = divmod(week_id, 100)
    try:
        week_start = date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid ISO week_id stored in database: {week_id}",
        ) from exc
    return week_start, date.fromordinal(week_start.toordinal() + 6)


def _database_unavailable(exc: Exception) -> HTTPException:
    logger.warning("Dashboard database query failed: %s", exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database temporarily unavailable; please retry shortly.",
        headers={"Retry-After": "5"},
    )


@router.get("/weeks", response_model=list[WeekResponse])
async def list_weeks(repository: RepositoryDependency) -> list[WeekResponse]:
    try:
        weeks = await repository.get_week_aggregations()
    except (SQLAlchemyError, ConnectionError, TimeoutError) as exc:
        raise _database_unavailable(exc) from exc

    response = []
    for item in weeks:
        week_start, week_end = _week_dates(item.week_id)
        response.append(
            WeekResponse(
                week_id=item.week_id,
                week_start=week_start,
                week_end=week_end,
                doc_count=item.doc_count,
                mention_count=item.mention_count,
                skus_covered=sorted(item.skus_covered),
            )
        )
    return response


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    repository: RepositoryDependency,
    week_id: Annotated[int, Query()],
) -> OverviewResponse:
    try:
        available_week_ids = await repository.get_week_ids()
        if week_id not in available_week_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No dashboard data found for week_id {week_id}.",
            )
        breakdown = await repository.get_sentiment_breakdown(week_id)
        top_aspects = await repository.get_top_aspects(week_id)
        rankings = await repository.get_sku_rankings(week_id)
    except HTTPException:
        raise
    except (SQLAlchemyError, ConnectionError, TimeoutError) as exc:
        raise _database_unavailable(exc) from exc

    total_mentions = sum(breakdown.values())
    return OverviewResponse(
        week_id=week_id,
        summary=OverviewSummaryResponse(
            total_mentions=total_mentions,
            sentiment_breakdown=SentimentBreakdownResponse(**breakdown),
        ),
        top_aspects=[
            TopAspectResponse(
                aspect_label=item.aspect_label,
                mention_count=item.count,
                positive_rate=item.positive_count / item.count if item.count else 0.0,
            )
            for item in top_aspects
        ],
        sku_rankings=[
            SkuRankingResponse(
                sku_code=item.sku_code,
                sku_name=item.sku_name,
                mention_count=item.mention_count,
                sentiment_score=(item.positive_count - item.negative_count)
                / item.mention_count
                if item.mention_count
                else 0.0,
            )
            for item in rankings
        ],
    )


@router.get("/skus/{sku_code}/trends", response_model=SkuTrendsResponse)
async def get_sku_trends(
    sku_code: str,
    repository: RepositoryDependency,
    weeks: Annotated[int, Query()] = 4,
) -> SkuTrendsResponse:
    if not 1 <= weeks <= 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="weeks must be between 1 and 12 (maximum: 12).",
        )

    try:
        enabled_skus = await repository.get_enabled_skus()
        sku = next((item for item in enabled_skus if item.sku_code == sku_code), None)
        if sku is None:
            valid_options = ", ".join(item.sku_code for item in enabled_skus)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unknown or disabled sku_code '{sku_code}'. "
                    f"Valid options: {valid_options}."
                ),
            )
        week_ids = await repository.get_week_ids(limit=weeks, sku_code=sku_code)
        trends = await repository.get_sku_trends(sku_code, week_ids)
    except HTTPException:
        raise
    except (SQLAlchemyError, ConnectionError, TimeoutError) as exc:
        raise _database_unavailable(exc) from exc

    return SkuTrendsResponse(
        sku_code=sku_code,
        sku_name=sku.sku_name,
        capacity_tier=sku.capacity_tier or "unknown",
        trends=[TrendPointResponse(**item.model_dump()) for item in trends],
    )
