"""Read-only PostgreSQL access for already-generated weekly reports."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Sku, WeeklyReport
from backend.app.db.repositories.schemas import SkuMetadata, WeeklyReportRow


class ReportRepository:
    """Expose report lookups only; report creation is intentionally out of scope."""

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
