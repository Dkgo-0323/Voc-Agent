from typing import Any

import pytest

from backend.app.agent.schemas import (
    AnalyticsOperation,
    AnalyticsToolArguments,
    AspectDistributionPayload,
    ReviewCountPayload,
    SentimentDistributionPayload,
    SkuComparisonPayload,
    ToolStatus,
    TrendPayload,
    WeekRange,
)
from backend.app.agent.tool_sql import AnalyticsService
from backend.app.core.settings import settings
from backend.app.db.repositories.analytics_repo import AnalyticsRepository
from backend.app.db.repositories.schemas import (
    AnalyticsComparisonRow,
    AnalyticsCountRow,
    AnalyticsDistributionRow,
    AnalyticsTrendRow,
    SkuMetadata,
)


def sku(code: str, tier: str) -> SkuMetadata:
    return SkuMetadata(
        sku_code=code,
        brand=code.split("-")[0].title(),
        model=code,
        capacity_wh=None,
        capacity_tier=tier,
        is_competitor=True,
        dashboard_enabled=True,
    )


class FakeAnalyticsRepository:
    def __init__(self) -> None:
        self.enabled = [
            sku("ecoflow-delta2", "mid"),
            sku("jackery-explorer-1000", "mid"),
            sku("anker-solix-f2000", "large"),
        ]
        self.counts = [
            AnalyticsCountRow(
                sku_code="ecoflow-delta2", review_count=30, mention_count=60
            ),
            AnalyticsCountRow(
                sku_code="jackery-explorer-1000", review_count=25, mention_count=40
            ),
        ]
        self.sentiments = [
            AnalyticsDistributionRow(label="positive", mention_count=60),
            AnalyticsDistributionRow(label="negative", mention_count=30),
            AnalyticsDistributionRow(label="neutral", mention_count=10),
        ]
        self.aspects = [
            AnalyticsDistributionRow(
                label="charging",
                mention_count=50,
                positive_count=30,
                negative_count=15,
                neutral_count=5,
            ),
            AnalyticsDistributionRow(
                label="noise",
                mention_count=30,
                positive_count=5,
                negative_count=20,
                neutral_count=5,
            ),
        ]
        self.trends = [
            AnalyticsTrendRow(
                week_id=202601,
                review_count=20,
                mention_count=40,
                positive_count=24,
                negative_count=12,
                neutral_count=4,
            ),
            AnalyticsTrendRow(
                week_id=202602,
                review_count=25,
                mention_count=60,
                positive_count=36,
                negative_count=18,
                neutral_count=6,
            ),
        ]
        self.comparison = [
            AnalyticsComparisonRow(
                sku_code="ecoflow-delta2",
                capacity_tier="mid",
                review_count=30,
                mention_count=60,
                positive_count=36,
                negative_count=18,
                neutral_count=6,
            ),
            AnalyticsComparisonRow(
                sku_code="jackery-explorer-1000",
                capacity_tier="mid",
                review_count=25,
                mention_count=40,
                positive_count=20,
                negative_count=16,
                neutral_count=4,
            ),
        ]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_enabled_skus(self) -> list[SkuMetadata]:
        return self.enabled

    async def get_counts(self, **kwargs) -> list[AnalyticsCountRow]:
        self.calls.append(("counts", kwargs))
        return self.counts

    async def get_sentiment_distribution(
        self, **kwargs
    ) -> list[AnalyticsDistributionRow]:
        self.calls.append(("sentiment", kwargs))
        return self.sentiments

    async def get_aspect_distribution(
        self, **kwargs
    ) -> list[AnalyticsDistributionRow]:
        self.calls.append(("aspect", kwargs))
        return self.aspects

    async def get_trend(self, **kwargs) -> list[AnalyticsTrendRow]:
        self.calls.append(("trend", kwargs))
        return self.trends

    async def get_comparison(self, **kwargs) -> list[AnalyticsComparisonRow]:
        self.calls.append(("comparison", kwargs))
        return self.comparison


@pytest.mark.asyncio
async def test_review_count_returns_exact_repository_counts() -> None:
    result = await AnalyticsService(FakeAnalyticsRepository()).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.REVIEW_COUNT,
            sku_codes=["ecoflow-delta2", "jackery-explorer-1000"],
        )
    )

    assert result.status is ToolStatus.SUCCESS
    assert isinstance(result.payload, ReviewCountPayload)
    assert result.payload.review_count == 55
    assert result.payload.mention_count == 100
    assert [item.review_count for item in result.payload.by_sku] == [30, 25]


@pytest.mark.asyncio
async def test_sentiment_distribution_calculates_counts_and_proportions() -> None:
    result = await AnalyticsService(FakeAnalyticsRepository()).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.SENTIMENT_DISTRIBUTION,
            sku_codes=["ecoflow-delta2", "jackery-explorer-1000"],
        )
    )

    assert isinstance(result.payload, SentimentDistributionPayload)
    assert result.payload.mention_count == 100
    assert [bucket.proportion for bucket in result.payload.distribution] == [0.6, 0.3, 0.1]


@pytest.mark.asyncio
async def test_aspect_distribution_keeps_dimension_counts_neutral() -> None:
    result = await AnalyticsService(FakeAnalyticsRepository()).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.ASPECT_DISTRIBUTION,
            sku_codes=["ecoflow-delta2", "jackery-explorer-1000"],
        )
    )

    assert isinstance(result.payload, AspectDistributionPayload)
    assert result.payload.distribution[0].model_dump() == {
        "aspect_label": "charging",
        "mention_count": 50,
        "proportion": 0.5,
        "positive_count": 30,
        "negative_count": 15,
        "neutral_count": 5,
    }


@pytest.mark.asyncio
async def test_trend_returns_weekly_counts_and_rates() -> None:
    result = await AnalyticsService(FakeAnalyticsRepository()).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.TREND,
            sku_codes=["ecoflow-delta2", "jackery-explorer-1000"],
        )
    )

    assert isinstance(result.payload, TrendPayload)
    assert [point.week_id for point in result.payload.points] == [202601, 202602]
    assert result.payload.points[0].positive_rate == 0.6
    assert result.payload.points[0].negative_rate == 0.3


@pytest.mark.asyncio
async def test_aspect_trend_passes_exact_aspect_filter_to_repository() -> None:
    repository = FakeAnalyticsRepository()
    result = await AnalyticsService(repository).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.ASPECT_TREND,
            sku_codes=["ecoflow-delta2"],
            aspect_label="noise",
        )
    )

    assert isinstance(result.payload, TrendPayload)
    assert result.payload.operation == "aspect_trend"
    assert result.payload.aspect_label == "noise"
    assert all(call[1]["aspect_label"] == "noise" for call in repository.calls)


@pytest.mark.asyncio
async def test_same_tier_comparison_returns_metrics_without_a_winner() -> None:
    result = await AnalyticsService(FakeAnalyticsRepository()).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.COMPARE_SKUS,
            sku_codes=["ecoflow-delta2", "jackery-explorer-1000"],
        )
    )

    assert result.status is ToolStatus.SUCCESS
    assert isinstance(result.payload, SkuComparisonPayload)
    assert result.payload.capacity_tier == "mid"
    assert result.payload.skus[0].sentiment_score == 0.3
    assert result.payload.skus[1].sentiment_score == 0.1
    assert "winner" not in result.payload.model_dump_json().lower()
    assert "better" not in result.payload.model_dump_json().lower()


@pytest.mark.asyncio
async def test_cross_tier_comparison_returns_machine_readable_constraint() -> None:
    repository = FakeAnalyticsRepository()
    result = await AnalyticsService(repository).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.COMPARE_SKUS,
            sku_codes=["ecoflow-delta2", "anker-solix-f2000"],
        )
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "capacity_tier_mismatch"
    assert result.error.details == {
        "ecoflow-delta2": "mid",
        "anker-solix-f2000": "large",
    }
    assert repository.calls == []


@pytest.mark.asyncio
async def test_low_sample_warns_without_blocking_query() -> None:
    repository = FakeAnalyticsRepository()
    repository.counts = [
        AnalyticsCountRow(
            sku_code="ecoflow-delta2", review_count=5, mention_count=10
        )
    ]
    result = await AnalyticsService(repository, min_reliable_sample=20).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.REVIEW_COUNT,
            sku_codes=["ecoflow-delta2"],
        )
    )

    assert result.status is ToolStatus.SUCCESS
    assert result.warnings[0].code == "small_sample"
    assert result.warnings[0].details == {
        "sku_code": "ecoflow-delta2",
        "sample_size": 5,
        "threshold": 20,
    }


@pytest.mark.asyncio
async def test_unknown_or_disabled_sku_is_rejected_before_query() -> None:
    repository = FakeAnalyticsRepository()
    result = await AnalyticsService(repository).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.REVIEW_COUNT,
            sku_codes=["not-enabled"],
        )
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "unknown_or_disabled_sku"
    assert repository.calls == []


@pytest.mark.asyncio
async def test_invalid_iso_week_is_rejected_before_query() -> None:
    repository = FakeAnalyticsRepository()
    result = await AnalyticsService(repository).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.REVIEW_COUNT,
            sku_codes=["ecoflow-delta2"],
            week_range=WeekRange(start_week_id=202699, end_week_id=202699),
        )
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "invalid_week_range"
    assert repository.calls == []


@pytest.mark.asyncio
async def test_no_matching_data_returns_structured_empty_result() -> None:
    repository = FakeAnalyticsRepository()
    repository.counts = []
    result = await AnalyticsService(repository).execute(
        AnalyticsToolArguments(
            operation=AnalyticsOperation.TREND,
            sku_codes=["ecoflow-delta2"],
        )
    )

    assert result.status is ToolStatus.EMPTY
    assert result.payload is None
    assert result.execution.result_count == 0


@pytest.mark.asyncio
async def test_repository_failure_returns_structured_retryable_error() -> None:
    repository = FakeAnalyticsRepository()

    async def fail():
        raise ConnectionError("database unavailable")

    repository.get_enabled_skus = fail
    result = await AnalyticsService(repository).execute(
        AnalyticsToolArguments(operation=AnalyticsOperation.REVIEW_COUNT)
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "analytics_query_failed"
    assert result.error.retryable is True


class EmptyResult:
    def __iter__(self):
        return iter([])


class CapturingSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return EmptyResult()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    [
        "get_counts",
        "get_sentiment_distribution",
        "get_aspect_distribution",
        "get_trend",
        "get_comparison",
    ],
)
async def test_every_repository_query_enforces_dashboard_and_quality_filters(
    method_name: str,
) -> None:
    session = CapturingSession()
    repository = AnalyticsRepository(session)
    await getattr(repository, method_name)(sku_codes=["ecoflow-delta2"])

    sql = str(session.statement)
    assert "skus.dashboard_enabled IS true" in sql
    assert "aspect_mentions.quality_score >=" in sql
    assert settings.aspect_quality_threshold in session.statement.compile().params.values()


@pytest.mark.asyncio
async def test_repository_binds_every_structured_scope_filter() -> None:
    session = CapturingSession()
    await AnalyticsRepository(session).get_trend(
        sku_codes=["ecoflow-delta2"],
        week_range=(202601, 202602),
        aspect_label="noise",
        sentiment="negative",
    )

    parameters = session.statement.compile().params.values()
    assert ["ecoflow-delta2"] in parameters
    assert 202601 in parameters
    assert 202602 in parameters
    assert "noise" in parameters
    assert "negative" in parameters
