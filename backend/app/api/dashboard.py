"""Dashboard endpoints backed by PostgreSQL aggregate queries."""

import logging
from datetime import date
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.schemas import (
    AnalyticsOperation,
    AnalyticsToolArguments,
    AnswerCitation,
    ExpandedSourceMetadata,
    ReportToolArguments,
    Sentiment,
    SkuComparisonMetrics,
    SkuComparisonPayload,
    ToolError,
    ToolStatus,
    ToolWarning,
    WeeklyReportPayload,
    WeekRange,
)
from backend.app.agent.tool_report import ReportService
from backend.app.agent.tool_sql import AnalyticsRepositoryProtocol, AnalyticsService
from backend.app.core.database import get_db
from backend.app.db.repositories.analytics_repo import AnalyticsRepository
from backend.app.db.repositories.aspect_repo import AspectRepository
from backend.app.db.repositories.report_repo import ReportRepository
from backend.app.db.repositories.schemas import RetrievedEvidenceRow, SkuMetadata

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


class SkuMetadataResponse(DashboardResponse):
    sku_code: str
    brand: str
    model: str
    capacity_wh: int | None
    capacity_tier: str | None
    is_competitor: bool
    dashboard_enabled: bool


class SkuDetailResponse(SkuMetadataResponse):
    week_id: int
    review_count: int = Field(ge=0)
    mention_count: int = Field(ge=0)
    sentiment_breakdown: SentimentBreakdownResponse
    top_aspects: list[TopAspectResponse]


class ComparisonResponse(DashboardResponse):
    week_id: int | None
    capacity_tier: str
    skus: list[SkuComparisonMetrics]
    warnings: list[ToolWarning]


class ClientToolErrorResponse(DashboardResponse):
    code: str
    message: str
    retryable: bool
    details: dict[str, str | int | float | bool | None]


def get_aspect_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AspectRepository:
    return AspectRepository(db)


RepositoryDependency = Annotated[AspectRepository, Depends(get_aspect_repository)]


def get_report_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReportService:
    return ReportService(ReportRepository(db))


def get_analytics_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalyticsService:
    # The concrete repository implements the fixed aggregate protocol at runtime.
    # Its explicit keyword-only signatures are narrower than the protocol's
    # forwarding signatures, so make that boundary explicit to static checkers.
    repository = cast(AnalyticsRepositoryProtocol, AnalyticsRepository(db))
    return AnalyticsService(repository)


ReportServiceDependency = Annotated[ReportService, Depends(get_report_service)]
AnalyticsServiceDependency = Annotated[AnalyticsService, Depends(get_analytics_service)]


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


def _sku_response(sku: SkuMetadata) -> SkuMetadataResponse:
    return SkuMetadataResponse(**sku.model_dump())


def _unknown_sku_error(sku_code: str, enabled_skus: list[SkuMetadata]) -> HTTPException:
    valid_options = ", ".join(item.sku_code for item in enabled_skus)
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Unknown or disabled sku_code '{sku_code}'. "
            f"Valid options: {valid_options}."
        ),
    )


def _citation_from_evidence(row: RetrievedEvidenceRow) -> AnswerCitation:
    return AnswerCitation(
        mention_id=row.mention_id,
        document_id=row.document_id,
        evidence_preview=row.mention_text,
        sku_code=row.sku_code,
        aspect_label=row.aspect_label,
        sentiment=Sentiment(row.sentiment),
        week_id=row.week_id,
        source=ExpandedSourceMetadata(
            document_id=row.document_id,
            sku_code=row.sku_code,
            platform=row.platform,
            published_at=row.published_at,
            source_url=row.source_url,
            title=row.title,
            rating=row.rating,
            review_text=row.review_text,
        ),
    )


def _tool_error_http(error: ToolError) -> HTTPException:
    return HTTPException(
        status_code=(
            status.HTTP_503_SERVICE_UNAVAILABLE
            if error.retryable
            else status.HTTP_400_BAD_REQUEST
        ),
        detail=ClientToolErrorResponse(**error.model_dump()).model_dump(mode="json"),
        headers={"Retry-After": "5"} if error.retryable else None,
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


@router.get("/skus", response_model=list[SkuMetadataResponse])
async def list_skus(repository: RepositoryDependency) -> list[SkuMetadataResponse]:
    """List only SKUs that the dashboard is allowed to expose."""
    try:
        return [_sku_response(sku) for sku in await repository.get_enabled_skus()]
    except (SQLAlchemyError, ConnectionError, TimeoutError) as exc:
        raise _database_unavailable(exc) from exc


@router.get("/skus/{sku_code}", response_model=SkuDetailResponse)
async def get_sku_detail(
    sku_code: str,
    repository: RepositoryDependency,
    week_id: Annotated[int, Query()],
) -> SkuDetailResponse:
    try:
        enabled_skus = await repository.get_enabled_skus()
        sku = next((item for item in enabled_skus if item.sku_code == sku_code), None)
        if sku is None:
            raise _unknown_sku_error(sku_code, enabled_skus)
        if week_id not in await repository.get_week_ids(sku_code=sku_code):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No dashboard data found for sku_code '{sku_code}' and week_id {week_id}.",
            )
        review_count, mention_count = await repository.get_sku_week_summary(
            sku_code=sku_code, week_id=week_id
        )
        breakdown = await repository.get_sentiment_breakdown(week_id, sku_code=sku_code)
        top_aspects = await repository.get_top_aspects(week_id, sku_code=sku_code)
    except HTTPException:
        raise
    except (SQLAlchemyError, ConnectionError, TimeoutError) as exc:
        raise _database_unavailable(exc) from exc

    return SkuDetailResponse(
        **sku.model_dump(),
        week_id=week_id,
        review_count=review_count,
        mention_count=mention_count,
        sentiment_breakdown=SentimentBreakdownResponse(**breakdown),
        top_aspects=[
            TopAspectResponse(
                aspect_label=item.aspect_label,
                mention_count=item.count,
                positive_rate=item.positive_count / item.count if item.count else 0.0,
            )
            for item in top_aspects
        ],
    )


@router.get("/skus/{sku_code}/evidence", response_model=list[AnswerCitation])
async def get_sku_evidence(
    sku_code: str,
    repository: RepositoryDependency,
    week_id: Annotated[int, Query()],
    sentiment: Sentiment,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[AnswerCitation]:
    try:
        enabled_skus = await repository.get_enabled_skus()
        if not any(item.sku_code == sku_code for item in enabled_skus):
            raise _unknown_sku_error(sku_code, enabled_skus)
        if week_id not in await repository.get_week_ids(sku_code=sku_code):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No dashboard data found for sku_code '{sku_code}' and week_id {week_id}.",
            )
        evidence = await repository.get_sku_evidence(
            sku_code=sku_code,
            week_id=week_id,
            sentiment=sentiment.value,
            limit=limit,
        )
    except HTTPException:
        raise
    except (SQLAlchemyError, ConnectionError, TimeoutError) as exc:
        raise _database_unavailable(exc) from exc
    return [_citation_from_evidence(row) for row in evidence]


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
            raise _unknown_sku_error(sku_code, enabled_skus)
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


@router.get("/compare", response_model=ComparisonResponse)
async def compare_skus(
    service: AnalyticsServiceDependency,
    sku_code: Annotated[list[str], Query(min_length=2)],
    week_id: Annotated[int | None, Query()] = None,
) -> ComparisonResponse:
    try:
        arguments = AnalyticsToolArguments(
            operation=AnalyticsOperation.COMPARE_SKUS,
            sku_codes=sku_code,
            week_range=(
                WeekRange(start_week_id=week_id, end_week_id=week_id)
                if week_id is not None
                else None
            ),
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    result = await service.execute(arguments)
    if result.status is ToolStatus.ERROR:
        assert result.error is not None
        raise _tool_error_http(result.error)
    if result.status is ToolStatus.EMPTY or result.payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No dashboard comparison data found for the requested scope.",
        )
    payload = result.payload
    assert isinstance(payload, SkuComparisonPayload)
    return ComparisonResponse(
        week_id=week_id,
        capacity_tier=payload.capacity_tier,
        skus=payload.skus,
        warnings=result.warnings,
    )


@router.get("/reports/{week_id}", response_model=WeeklyReportPayload)
async def get_weekly_report(
    week_id: int,
    service: ReportServiceDependency,
    sku_code: Annotated[str, Query(min_length=1)],
) -> WeeklyReportPayload:
    try:
        arguments = ReportToolArguments(sku_code=sku_code, week_id=week_id)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    result = await service.execute(arguments)
    if result.status is ToolStatus.ERROR:
        assert result.error is not None
        raise _tool_error_http(result.error)
    if result.status is ToolStatus.NOT_FOUND or result.payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stored weekly report found for sku_code '{sku_code}' and week_id {week_id}.",
        )
    return result.payload
