"""PostgreSQL access for stored weekly reports."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Sku, WeeklyReport
from backend.app.db.repositories.schemas import SkuMetadata, WeeklyReportRow


class ReportRepository:
    """Read reports and stage validated replacements in the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_enabled_skus(self) -> list[SkuMetadata]:
        result = await self._session.execute(
            select(Sku).where(Sku.dashboard_enabled.is_(True)).order_by(Sku.sku_code)
        )
        return [SkuMetadata.model_validate(sku) for sku in result.scalars()]

    async def get_weekly_report(
        self, *, sku_code: str, week_id: int
    ) -> WeeklyReportRow | None:
        statement = (
            select(
                WeeklyReport.id.label("report_id"),
                Sku.sku_code,
                WeeklyReport.week_id,
                WeeklyReport.report_md,
                WeeklyReport.summary,
                WeeklyReport.generated_at,
            )
            .join(Sku, Sku.id == WeeklyReport.sku_id)
            .where(
                Sku.sku_code == sku_code,
                Sku.dashboard_enabled.is_(True),
                WeeklyReport.week_id == week_id,
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        return WeeklyReportRow.model_validate(row._mapping) if row is not None else None

    async def save_weekly_report(
        self,
        *,
        sku_code: str,
        week_id: int,
        report_md: str,
        summary: str,
    ) -> WeeklyReportRow:
        """Insert or replace one report without committing the surrounding transaction."""

        sku = (
            await self._session.execute(
                select(Sku).where(
                    Sku.sku_code == sku_code,
                    Sku.dashboard_enabled.is_(True),
                )
            )
        ).scalar_one()
        report = (
            await self._session.execute(
                select(WeeklyReport).where(
                    WeeklyReport.sku_id == sku.id,
                    WeeklyReport.week_id == week_id,
                )
            )
        ).scalar_one_or_none()
        generated_at = datetime.now(UTC).replace(tzinfo=None)
        if report is None:
            report = WeeklyReport(
                sku_id=sku.id,
                week_id=week_id,
                report_md=report_md,
                summary=summary,
                generated_at=generated_at,
            )
            self._session.add(report)
        else:
            report.report_md = report_md
            report.summary = summary
            report.generated_at = generated_at
        await self._session.flush()
        return WeeklyReportRow(
            report_id=report.id,
            sku_code=sku_code,
            week_id=week_id,
            report_md=report.report_md,
            summary=report.summary,
            generated_at=report.generated_at,
        )
