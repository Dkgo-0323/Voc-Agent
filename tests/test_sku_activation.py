import pytest

from backend.app.db.migrations.versions import (
    f7a8b9c0d1e2_add_sku_dashboard_enabled as migration,
)
from backend.app.db.repositories.aspect_repo import AspectRepository
from backend.app.db.repositories.document_repo import DocumentRepository
from backend.app.db.seed import SKU_DATA, SKU_UPSERT_SQL
from pipelines.config.targets import LOCKED_SKU_CODES, TARGETS


class EmptyResult:
    def __iter__(self):
        return iter([])

    def scalars(self):
        return self


class CapturingSession:
    def __init__(self, result=None) -> None:
        self.statement = None
        self.result = result if result is not None else EmptyResult()

    async def execute(self, statement):
        self.statement = statement
        return self.result


def test_migration_soft_enables_only_locked_skus(monkeypatch) -> None:
    added_columns = []
    executed_sql = []
    indexes = []
    monkeypatch.setattr(
        migration.op,
        "add_column",
        lambda table, column: added_columns.append((table, column)),
    )
    monkeypatch.setattr(
        migration.op, "execute", lambda sql: executed_sql.append(str(sql))
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns: indexes.append((name, table, columns)),
    )

    migration.upgrade()

    assert added_columns[0][0] == "skus"
    assert added_columns[0][1].name == "dashboard_enabled"
    assert all(code in executed_sql[0] for code in LOCKED_SKU_CODES)
    assert "DELETE" not in executed_sql[0].upper()
    assert indexes == [("ix_skus_dashboard_enabled", "skus", ["dashboard_enabled"])]


def test_seed_upserts_enabled_state_without_deleting_unknown_skus() -> None:
    sql = str(SKU_UPSERT_SQL)

    assert {item["sku_code"] for item in SKU_DATA} == set(LOCKED_SKU_CODES)
    assert all(item["dashboard_enabled"] is True for item in SKU_DATA)
    assert "dashboard_enabled = EXCLUDED.dashboard_enabled" in sql
    assert "DELETE" not in sql.upper()


def test_targets_only_contains_collection_configuration() -> None:
    allowed_keys = {"amazon_asins", "reddit_keywords", "reddit_subreddits"}

    assert set(TARGETS) == set(LOCKED_SKU_CODES)
    assert all(set(config) == allowed_keys for config in TARGETS.values())


@pytest.mark.asyncio
async def test_document_repository_filters_disabled_skus_by_default() -> None:
    session = CapturingSession()
    repository = DocumentRepository(session)

    await repository.fetch_unprocessed(10)

    assert "skus.dashboard_enabled IS true" in str(session.statement)


@pytest.mark.asyncio
async def test_document_repository_can_include_disabled_for_diagnostics() -> None:
    session = CapturingSession()
    repository = DocumentRepository(session)

    await repository.fetch_by_status("raw", include_disabled=True)

    assert "dashboard_enabled" not in str(session.statement)


@pytest.mark.asyncio
async def test_dashboard_aggregation_filters_disabled_skus_by_default() -> None:
    session = CapturingSession()

    await AspectRepository(session).get_week_aggregations()

    assert "skus.dashboard_enabled IS true" in str(session.statement)
    assert "aspect_mentions.quality_score >=" in str(session.statement)


@pytest.mark.asyncio
async def test_locked_sku_consistency_check_reports_missing_and_disabled() -> None:
    result = [
        ("ecoflow-delta2", True),
        ("jackery-explorer-1000", False),
    ]
    repository = AspectRepository(CapturingSession(result))

    with pytest.raises(RuntimeError, match="missing=.*disabled="):
        await repository.validate_locked_skus(
            {"ecoflow-delta2", "jackery-explorer-1000", "anker-solix-f2000"}
        )
