from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.sql import Select

from backend.app.agent.schemas import ReportToolArguments, ToolName, ToolStatus
from backend.app.agent.tool_report import ReportService
from backend.app.db.repositories.report_repo import ReportRepository
from backend.app.db.repositories.schemas import SkuMetadata, WeeklyReportRow


def enabled_sku(sku_code: str = "ecoflow-delta2") -> SkuMetadata:
    return SkuMetadata(
        sku_code=sku_code,
        brand="EcoFlow",
        model="Delta 2",
        capacity_wh=1024,
        capacity_tier="mid",
        is_competitor=False,
        dashboard_enabled=True,
    )


class FakeReportRepository:
    def __init__(self, report: WeeklyReportRow | None = None) -> None:
        self.report = report
        self.calls: list[tuple] = []

    async def get_enabled_skus(self) -> list[SkuMetadata]:
        self.calls.append(("get_enabled_skus",))
        return [enabled_sku()]

    async def get_weekly_report(
        self, *, sku_code: str, week_id: int
    ) -> WeeklyReportRow | None:
        self.calls.append(("get_weekly_report", sku_code, week_id))
        return self.report


@pytest.mark.asyncio
async def test_existing_report_returns_stored_content_and_identifiers_verbatim() -> (
    None
):
    report_id = uuid4()
    generated_at = datetime(2026, 8, 24, 9, 30, tzinfo=UTC)
    repository = FakeReportRepository(
        WeeklyReportRow(
            report_id=report_id,
            sku_code="ecoflow-delta2",
            week_id=202635,
            report_md="# Stored report\n\nExact persisted content.",
            summary="Persisted summary.",
            generated_at=generated_at,
        )
    )

    result = await ReportService(repository).execute(
        ReportToolArguments(sku_code="ecoflow-delta2", week_id=202635)
    )

    assert result.status is ToolStatus.SUCCESS
    assert result.tool_name is ToolName.REPORT
    assert result.execution.result_count == 1
    assert result.payload is not None
    assert result.payload.model_dump() == {
        "report_id": report_id,
        "sku_code": "ecoflow-delta2",
        "week_id": 202635,
        "report_md": "# Stored report\n\nExact persisted content.",
        "summary": "Persisted summary.",
        "generated_at": generated_at,
    }


@pytest.mark.asyncio
async def test_existing_empty_content_is_not_replaced_with_generated_text() -> None:
    repository = FakeReportRepository(
        WeeklyReportRow(
            report_id=uuid4(),
            sku_code="ecoflow-delta2",
            week_id=202635,
            report_md=None,
            summary=None,
            generated_at=datetime(2026, 8, 24, 9, 30, tzinfo=UTC),
        )
    )

    result = await ReportService(repository).execute(
        ReportToolArguments(sku_code="ecoflow-delta2", week_id=202635)
    )

    assert result.status is ToolStatus.SUCCESS
    assert result.payload is not None
    assert result.payload.report_md is None
    assert result.payload.summary is None


@pytest.mark.asyncio
async def test_missing_report_returns_structured_not_found_without_fallback() -> None:
    repository = FakeReportRepository()

    result = await ReportService(repository).execute(
        ReportToolArguments(sku_code="ecoflow-delta2", week_id=202635)
    )

    assert result.status is ToolStatus.NOT_FOUND
    assert result.payload is None
    assert result.error is None
    assert result.execution.result_count == 0
    assert repository.calls == [
        ("get_enabled_skus",),
        ("get_weekly_report", "ecoflow-delta2", 202635),
    ]


@pytest.mark.asyncio
async def test_invalid_week_is_rejected_before_repository_access() -> None:
    repository = FakeReportRepository()

    result = await ReportService(repository).execute(
        ReportToolArguments(sku_code="ecoflow-delta2", week_id=202399)
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "invalid_week_id"
    assert repository.calls == []


@pytest.mark.asyncio
async def test_unknown_sku_is_rejected_without_report_lookup() -> None:
    repository = FakeReportRepository()

    result = await ReportService(repository).execute(
        ReportToolArguments(sku_code="not-a-locked-sku", week_id=202635)
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "unknown_or_disabled_sku"
    assert repository.calls == [("get_enabled_skus",)]


def test_blank_report_identifier_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError, match="sku_code must not be blank"):
        ReportToolArguments(sku_code="   ", week_id=202635)


class EmptyLookupResult:
    def one_or_none(self):
        return None


class CapturingReadOnlySession:
    def __init__(self) -> None:
        self.statement = None
        self.execute_count = 0

    async def execute(self, statement):
        self.statement = statement
        self.execute_count += 1
        return EmptyLookupResult()


@pytest.mark.asyncio
async def test_repository_uses_one_select_and_has_no_generation_side_effect() -> None:
    session = CapturingReadOnlySession()

    report = await ReportRepository(session).get_weekly_report(
        sku_code="ecoflow-delta2", week_id=202635
    )

    assert report is None
    assert session.execute_count == 1
    assert isinstance(session.statement, Select)
    sql = str(session.statement)
    assert sql.lstrip().startswith("SELECT")
    assert "weekly_reports" in sql
    assert "skus.dashboard_enabled IS true" in sql
    parameters = session.statement.compile().params.values()
    assert "ecoflow-delta2" in parameters
    assert 202635 in parameters
