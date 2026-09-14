"""Read-only access to stored weekly reports."""

from __future__ import annotations

from datetime import date
from time import perf_counter
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from backend.app.agent.schemas import (
    ReportToolArguments,
    ReportToolResult,
    ToolError,
    ToolExecutionMetadata,
    ToolName,
    ToolStatus,
    WeeklyReportPayload,
)
from backend.app.db.repositories.schemas import SkuMetadata, WeeklyReportRow
from pipelines.config.targets import LOCKED_SKU_CODES


class ReportRepositoryProtocol(Protocol):
    async def get_enabled_skus(self) -> list[SkuMetadata]: ...

    async def get_weekly_report(
        self, *, sku_code: str, week_id: int
    ) -> WeeklyReportRow | None: ...


def _is_valid_iso_week(week_id: int) -> bool:
    year, week = divmod(week_id, 100)
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        return False
    return True


class ReportService:
    """Return stored report content without generating or synthesizing a fallback."""

    def __init__(self, repository: ReportRepositoryProtocol) -> None:
        self._repository = repository

    async def execute(self, arguments: ReportToolArguments) -> ReportToolResult:
        started = perf_counter()
        normalized_args = arguments.model_copy(
            update={"sku_code": arguments.sku_code.strip()}
        )
        if not _is_valid_iso_week(normalized_args.week_id):
            return self._error(
                normalized_args,
                started,
                code="invalid_week_id",
                message="week_id must be a valid ISO week identifier.",
                details={"week_id": normalized_args.week_id},
            )

        try:
            enabled_skus = await self._repository.get_enabled_skus()
        except (SQLAlchemyError, ConnectionError, TimeoutError):
            return self._error(
                normalized_args,
                started,
                code="report_query_failed",
                message="Stored weekly reports are temporarily unavailable.",
                retryable=True,
            )
        enabled_locked_codes = {
            sku.sku_code for sku in enabled_skus if sku.sku_code in LOCKED_SKU_CODES
        }
        if normalized_args.sku_code not in enabled_locked_codes:
            return self._error(
                normalized_args,
                started,
                code="unknown_or_disabled_sku",
                message="SKU is not locked and dashboard-enabled.",
                details={"sku_code": normalized_args.sku_code},
            )

        try:
            report = await self._repository.get_weekly_report(
                sku_code=normalized_args.sku_code,
                week_id=normalized_args.week_id,
            )
        except (SQLAlchemyError, ConnectionError, TimeoutError):
            return self._error(
                normalized_args,
                started,
                code="report_query_failed",
                message="Stored weekly reports are temporarily unavailable.",
                retryable=True,
            )
        if report is None:
            return ReportToolResult(
                status=ToolStatus.NOT_FOUND,
                tool_name=ToolName.REPORT,
                normalized_args=normalized_args,
                execution=self._execution(started, 0),
            )

        return ReportToolResult(
            status=ToolStatus.SUCCESS,
            tool_name=ToolName.REPORT,
            normalized_args=normalized_args,
            execution=self._execution(started, 1),
            payload=WeeklyReportPayload(
                report_id=report.report_id,
                sku_code=report.sku_code,
                week_id=report.week_id,
                report_md=report.report_md,
                summary=report.summary,
                generated_at=report.generated_at,
            ),
        )

    @staticmethod
    def _execution(started: float, count: int) -> ToolExecutionMetadata:
        return ToolExecutionMetadata(
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
            result_count=count,
        )

    @classmethod
    def _error(
        cls,
        arguments: ReportToolArguments,
        started: float,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> ReportToolResult:
        return ReportToolResult(
            status=ToolStatus.ERROR,
            tool_name=ToolName.REPORT,
            normalized_args=arguments,
            execution=cls._execution(started, 0),
            error=ToolError(
                code=code,
                message=message,
                retryable=retryable,
                details=details or {},
            ),
        )
