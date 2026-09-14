"""Deterministic analytics dispatcher exposed historically as ``tool_sql``."""

from __future__ import annotations

from datetime import date
from time import perf_counter
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from backend.app.agent.schemas import (
    AnalyticsOperation,
    AnalyticsToolArguments,
    AnalyticsToolResult,
    AspectBucket,
    AspectDistributionPayload,
    ReviewCountPayload,
    Sentiment,
    SentimentBucket,
    SentimentDistributionPayload,
    SkuComparisonMetrics,
    SkuComparisonPayload,
    SkuSampleCount,
    ToolError,
    ToolExecutionMetadata,
    ToolName,
    ToolStatus,
    ToolWarning,
    TrendPayload,
    TrendPoint,
)
from backend.app.core.settings import settings
from backend.app.db.repositories.schemas import (
    AnalyticsComparisonRow,
    AnalyticsCountRow,
    AnalyticsDistributionRow,
    AnalyticsTrendRow,
    SkuMetadata,
)


class AnalyticsRepositoryProtocol(Protocol):
    async def get_enabled_skus(self) -> list[SkuMetadata]: ...

    async def get_counts(self, **kwargs) -> list[AnalyticsCountRow]: ...

    async def get_sentiment_distribution(
        self, **kwargs
    ) -> list[AnalyticsDistributionRow]: ...

    async def get_aspect_distribution(
        self, **kwargs
    ) -> list[AnalyticsDistributionRow]: ...

    async def get_trend(self, **kwargs) -> list[AnalyticsTrendRow]: ...

    async def get_comparison(self, **kwargs) -> list[AnalyticsComparisonRow]: ...


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _week_tuple(arguments: AnalyticsToolArguments) -> tuple[int, int] | None:
    if arguments.week_range is None:
        return None
    return (
        arguments.week_range.start_week_id,
        arguments.week_range.end_week_id,
    )


def _is_valid_iso_week(week_id: int) -> bool:
    year, week = divmod(week_id, 100)
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        return False
    return True


class AnalyticsService:
    """Validate and execute approved aggregate operations without an LLM."""

    def __init__(
        self,
        repository: AnalyticsRepositoryProtocol,
        *,
        min_reliable_sample: int = settings.min_reliable_sample,
    ) -> None:
        if min_reliable_sample < 1:
            raise ValueError("min_reliable_sample must be positive")
        self._repository = repository
        self._min_reliable_sample = min_reliable_sample

    async def execute(self, arguments: AnalyticsToolArguments) -> AnalyticsToolResult:
        started = perf_counter()
        try:
            enabled_skus = await self._repository.get_enabled_skus()
        except (SQLAlchemyError, ConnectionError, TimeoutError):
            return self._error_result(
                arguments,
                started,
                code="analytics_query_failed",
                message="Analytics data is temporarily unavailable.",
                retryable=True,
            )
        enabled_by_code = {sku.sku_code: sku for sku in enabled_skus}
        requested_codes = arguments.sku_codes or list(enabled_by_code)
        normalized_args = arguments.model_copy(update={"sku_codes": requested_codes})

        unknown_codes = [code for code in requested_codes if code not in enabled_by_code]
        if unknown_codes:
            return self._error_result(
                normalized_args,
                started,
                code="unknown_or_disabled_sku",
                message="One or more SKU codes are unknown or not dashboard-enabled.",
                details={"sku_codes": ",".join(unknown_codes)},
            )

        if normalized_args.week_range is not None:
            invalid_weeks = [
                week_id
                for week_id in (
                    normalized_args.week_range.start_week_id,
                    normalized_args.week_range.end_week_id,
                )
                if not _is_valid_iso_week(week_id)
            ]
            if invalid_weeks:
                return self._error_result(
                    normalized_args,
                    started,
                    code="invalid_week_range",
                    message="Week range contains an invalid ISO week identifier.",
                    details={"week_ids": ",".join(map(str, invalid_weeks))},
                )

        if normalized_args.operation is AnalyticsOperation.COMPARE_SKUS:
            constraint_error = self._validate_capacity_tier(
                normalized_args, enabled_by_code, started
            )
            if constraint_error is not None:
                return constraint_error

        scope = {
            "sku_codes": normalized_args.sku_codes,
            "week_range": _week_tuple(normalized_args),
            "aspect_label": normalized_args.aspect_label,
            "sentiment": (
                normalized_args.sentiment.value if normalized_args.sentiment else None
            ),
        }
        try:
            count_rows = await self._repository.get_counts(**scope)
            if not count_rows or sum(row.mention_count for row in count_rows) == 0:
                return AnalyticsToolResult(
                    status=ToolStatus.EMPTY,
                    tool_name=ToolName.SQL,
                    normalized_args=normalized_args,
                    execution=self._execution(started, result_count=0),
                )
            warnings, partial = self._sample_warnings(
                normalized_args.sku_codes, count_rows
            )
            payload, result_count = await self._dispatch(
                normalized_args, scope, count_rows, enabled_by_code
            )
        except (SQLAlchemyError, ConnectionError, TimeoutError):
            return self._error_result(
                normalized_args,
                started,
                code="analytics_query_failed",
                message="Analytics data is temporarily unavailable.",
                retryable=True,
            )

        return AnalyticsToolResult(
            status=ToolStatus.PARTIAL if partial else ToolStatus.SUCCESS,
            tool_name=ToolName.SQL,
            normalized_args=normalized_args,
            warnings=warnings,
            execution=self._execution(started, result_count=result_count),
            payload=payload,
        )

    async def _dispatch(
        self,
        arguments: AnalyticsToolArguments,
        scope: dict,
        count_rows: list[AnalyticsCountRow],
        enabled_by_code: dict[str, SkuMetadata],
    ):
        if arguments.operation is AnalyticsOperation.REVIEW_COUNT:
            by_code = {row.sku_code: row for row in count_rows}
            by_sku = []
            for code in arguments.sku_codes:
                row = by_code.get(
                    code,
                    AnalyticsCountRow(
                        sku_code=code, review_count=0, mention_count=0
                    ),
                )
                by_sku.append(
                    SkuSampleCount(
                        sku_code=code,
                        review_count=row.review_count,
                        mention_count=row.mention_count,
                    )
                )
            return (
                ReviewCountPayload(
                    review_count=sum(item.review_count for item in by_sku),
                    mention_count=sum(item.mention_count for item in by_sku),
                    by_sku=by_sku,
                ),
                len(by_sku),
            )

        if arguments.operation is AnalyticsOperation.SENTIMENT_DISTRIBUTION:
            rows = await self._repository.get_sentiment_distribution(**scope)
            total = sum(row.mention_count for row in rows)
            by_sentiment = {row.label: row.mention_count for row in rows}
            distribution = [
                SentimentBucket(
                    sentiment=sentiment,
                    mention_count=by_sentiment.get(sentiment.value, 0),
                    proportion=_ratio(by_sentiment.get(sentiment.value, 0), total),
                )
                for sentiment in Sentiment
            ]
            return (
                SentimentDistributionPayload(
                    mention_count=total, distribution=distribution
                ),
                len(distribution),
            )

        if arguments.operation is AnalyticsOperation.ASPECT_DISTRIBUTION:
            rows = await self._repository.get_aspect_distribution(
                **scope, limit=arguments.limit
            )
            total = sum(row.mention_count for row in count_rows)
            distribution = [
                AspectBucket(
                    aspect_label=row.label,
                    mention_count=row.mention_count,
                    proportion=_ratio(row.mention_count, total),
                    positive_count=row.positive_count,
                    negative_count=row.negative_count,
                    neutral_count=row.neutral_count,
                )
                for row in rows
            ]
            return (
                AspectDistributionPayload(
                    mention_count=total, distribution=distribution
                ),
                len(distribution),
            )

        if arguments.operation in {
            AnalyticsOperation.TREND,
            AnalyticsOperation.ASPECT_TREND,
        }:
            rows = await self._repository.get_trend(**scope)
            points = [self._trend_point(row) for row in rows]
            return (
                TrendPayload(
                    operation=arguments.operation.value,
                    aspect_label=arguments.aspect_label,
                    points=points,
                ),
                len(points),
            )

        rows = await self._repository.get_comparison(**scope)
        rows_by_code = {row.sku_code: row for row in rows}
        comparison_rows = [
            self._comparison_metrics(
                rows_by_code.get(
                    code,
                    AnalyticsComparisonRow(
                        sku_code=code,
                        capacity_tier=enabled_by_code[code].capacity_tier,
                        review_count=0,
                        mention_count=0,
                        positive_count=0,
                        negative_count=0,
                        neutral_count=0,
                    ),
                )
            )
            for code in arguments.sku_codes
        ]
        return (
            SkuComparisonPayload(
                capacity_tier=enabled_by_code[arguments.sku_codes[0]].capacity_tier
                or "unknown",
                comparison_metric=arguments.comparison_metric,
                skus=comparison_rows,
            ),
            len(comparison_rows),
        )

    def _validate_capacity_tier(
        self,
        arguments: AnalyticsToolArguments,
        enabled_by_code: dict[str, SkuMetadata],
        started: float,
    ) -> AnalyticsToolResult | None:
        tiers = {
            code: enabled_by_code[code].capacity_tier for code in arguments.sku_codes
        }
        if any(tier is None for tier in tiers.values()):
            return self._error_result(
                arguments,
                started,
                code="capacity_tier_unavailable",
                message="Capacity tier metadata is unavailable for comparison.",
                details={code: tier or "unknown" for code, tier in tiers.items()},
            )
        if len(set(tiers.values())) != 1:
            return self._error_result(
                arguments,
                started,
                code="capacity_tier_mismatch",
                message="Direct SKU comparison requires the same capacity tier.",
                details={code: tier for code, tier in tiers.items()},
            )
        return None

    def _sample_warnings(
        self, sku_codes: list[str], rows: list[AnalyticsCountRow]
    ) -> tuple[list[ToolWarning], bool]:
        by_code = {row.sku_code: row for row in rows}
        warnings: list[ToolWarning] = []
        partial = False
        for code in sku_codes:
            sample_size = by_code.get(
                code, AnalyticsCountRow(sku_code=code, review_count=0, mention_count=0)
            ).review_count
            if sample_size == 0:
                partial = True
                warnings.append(
                    ToolWarning(
                        code="no_matching_data",
                        message=f"No matching analytics data for {code}.",
                        details={"sku_code": code, "sample_size": 0},
                    )
                )
            elif sample_size < self._min_reliable_sample:
                warnings.append(
                    ToolWarning(
                        code="small_sample",
                        message=(
                            f"{code} has {sample_size} matching reviews, below the "
                            f"reliability threshold of {self._min_reliable_sample}."
                        ),
                        details={
                            "sku_code": code,
                            "sample_size": sample_size,
                            "threshold": self._min_reliable_sample,
                        },
                    )
                )
        return warnings, partial

    @staticmethod
    def _trend_point(row: AnalyticsTrendRow) -> TrendPoint:
        return TrendPoint(
            **row.model_dump(),
            positive_rate=_ratio(row.positive_count, row.mention_count),
            negative_rate=_ratio(row.negative_count, row.mention_count),
            neutral_rate=_ratio(row.neutral_count, row.mention_count),
        )

    @staticmethod
    def _comparison_metrics(row: AnalyticsComparisonRow) -> SkuComparisonMetrics:
        return SkuComparisonMetrics(
            sku_code=row.sku_code,
            review_count=row.review_count,
            mention_count=row.mention_count,
            positive_count=row.positive_count,
            negative_count=row.negative_count,
            neutral_count=row.neutral_count,
            positive_rate=_ratio(row.positive_count, row.mention_count),
            negative_rate=_ratio(row.negative_count, row.mention_count),
            neutral_rate=_ratio(row.neutral_count, row.mention_count),
            sentiment_score=_ratio(
                row.positive_count - row.negative_count, row.mention_count
            ),
        )

    @staticmethod
    def _execution(started: float, *, result_count: int) -> ToolExecutionMetadata:
        return ToolExecutionMetadata(
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
            result_count=result_count,
        )

    @classmethod
    def _error_result(
        cls,
        arguments: AnalyticsToolArguments,
        started: float,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> AnalyticsToolResult:
        return AnalyticsToolResult(
            status=ToolStatus.ERROR,
            tool_name=ToolName.SQL,
            normalized_args=arguments,
            execution=cls._execution(started, result_count=0),
            error=ToolError(
                code=code,
                message=message,
                retryable=retryable,
                details=details or {},
            ),
        )
