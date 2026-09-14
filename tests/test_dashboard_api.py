from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app.agent.tool_report import ReportService
from backend.app.agent.tool_sql import AnalyticsService
from backend.app.api.dashboard import (
    get_analytics_service,
    get_aspect_repository,
    get_report_service,
)
from backend.app.db.repositories.schemas import (
    AnalyticsComparisonRow,
    AnalyticsCountRow,
    RetrievedEvidenceRow,
    SkuMetadata,
    SkuRanking,
    SkuTrend,
    TopAspect,
    WeekAggregation,
    WeeklyReportRow,
)
from backend.app.main import app


class FakeAspectRepository:
    def __init__(self) -> None:
        self.requested_trend_weeks: list[int] = []

    async def get_week_aggregations(self) -> list[WeekAggregation]:
        return [
            WeekAggregation(
                week_id=202403,
                doc_count=12,
                mention_count=20,
                skus_covered=["jackery-explorer-1000", "ecoflow-delta2"],
            )
        ]

    async def get_enabled_skus(self) -> list[SkuMetadata]:
        return [
            SkuMetadata(
                sku_code="ecoflow-delta2",
                brand="EcoFlow",
                model="DELTA 2",
                capacity_wh=1024,
                capacity_tier="mid",
                is_competitor=False,
                dashboard_enabled=True,
            )
        ]

    async def get_week_ids(
        self, *, limit: int | None = None, sku_code: str | None = None
    ) -> list[int]:
        week_ids = [202403, 202402, 202401]
        return week_ids[:limit] if limit is not None else week_ids

    async def get_sentiment_breakdown(
        self, week_id: int, sku_code: str | None = None
    ) -> dict[str, int]:
        return {"positive": 10, "negative": 4, "neutral": 6}

    async def get_top_aspects(
        self, week_id: int, sku_code: str | None = None, limit: int = 10
    ) -> list[TopAspect]:
        return [
            TopAspect(
                aspect_label="battery_capacity",
                count=10,
                positive_count=7,
                avg_sentiment_score=0.5,
            )
        ]

    async def get_sku_rankings(self, week_id: int) -> list[SkuRanking]:
        return [
            SkuRanking(
                sku_code="ecoflow-delta2",
                sku_name="EcoFlow DELTA 2",
                mention_count=10,
                positive_count=7,
                negative_count=2,
            )
        ]

    async def get_sku_trends(
        self, sku_code: str, week_ids: list[int]
    ) -> list[SkuTrend]:
        self.requested_trend_weeks = week_ids
        return [
            SkuTrend(
                week_id=202403,
                aspect_label="battery_capacity",
                positive_count=7,
                negative_count=2,
                neutral_count=1,
                avg_quality_score=0.74,
            )
        ]

    async def get_sku_week_summary(
        self, *, sku_code: str, week_id: int
    ) -> tuple[int, int]:
        return 12, 20

    async def get_sku_evidence(
        self,
        *,
        sku_code: str,
        week_id: int,
        sentiment: str,
        limit: int,
    ) -> list[RetrievedEvidenceRow]:
        return [
            RetrievedEvidenceRow(
                mention_id=UUID("00000000-0000-0000-0000-000000000101"),
                document_id=UUID("00000000-0000-0000-0000-000000000201"),
                sku_code=sku_code,
                aspect_label="battery_capacity",
                sentiment=sentiment,
                mention_text="It lasted through the whole weekend.",
                context_window=None,
                quality_score=0.91,
                week_id=week_id,
                platform="reddit",
                published_at=None,
                source_url="https://example.test/review/201",
                title="Weekend power",
                rating=None,
                review_text="It lasted through the whole weekend.",
            )
        ][:limit]


class FakeAnalyticsRepository:
    async def get_enabled_skus(self) -> list[SkuMetadata]:
        return [
            SkuMetadata(
                sku_code="ecoflow-delta2",
                brand="EcoFlow",
                model="DELTA 2",
                capacity_wh=1024,
                capacity_tier="mid",
                is_competitor=False,
                dashboard_enabled=True,
            ),
            SkuMetadata(
                sku_code="jackery-explorer-1000",
                brand="Jackery",
                model="Explorer 1000",
                capacity_wh=1002,
                capacity_tier="mid",
                is_competitor=True,
                dashboard_enabled=True,
            ),
            SkuMetadata(
                sku_code="anker-solix-f2000",
                brand="Anker",
                model="SOLIX F2000",
                capacity_wh=2048,
                capacity_tier="large",
                is_competitor=True,
                dashboard_enabled=True,
            ),
        ]

    async def get_counts(self, **kwargs) -> list[AnalyticsCountRow]:
        return [
            AnalyticsCountRow(sku_code=code, review_count=22, mention_count=30)
            for code in kwargs["sku_codes"]
        ]

    async def get_comparison(self, **kwargs) -> list[AnalyticsComparisonRow]:
        return [
            AnalyticsComparisonRow(
                sku_code=code,
                capacity_tier="mid",
                review_count=22,
                mention_count=30,
                positive_count=18,
                negative_count=6,
                neutral_count=6,
            )
            for code in kwargs["sku_codes"]
        ]


class FakeReportRepository:
    async def get_enabled_skus(self) -> list[SkuMetadata]:
        return await FakeAnalyticsRepository().get_enabled_skus()

    async def get_weekly_report(
        self, *, sku_code: str, week_id: int
    ) -> WeeklyReportRow | None:
        if week_id != 202403:
            return None
        return WeeklyReportRow(
            report_id=UUID("00000000-0000-0000-0000-000000000301"),
            sku_code=sku_code,
            week_id=week_id,
            report_md="# Stored report",
            summary="Stored summary",
            generated_at=datetime(2024, 1, 22, tzinfo=UTC),
        )


@pytest.fixture
def repository() -> FakeAspectRepository:
    return FakeAspectRepository()


@pytest.fixture
def client(repository: FakeAspectRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_aspect_repository] = lambda: repository
    app.dependency_overrides[get_analytics_service] = lambda: AnalyticsService(
        FakeAnalyticsRepository(), min_reliable_sample=20
    )
    app.dependency_overrides[get_report_service] = lambda: ReportService(
        FakeReportRepository()
    )
    test_client = TestClient(app, raise_server_exceptions=False)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


def test_weeks_returns_iso_bounds_and_sorted_skus(client: TestClient) -> None:
    response = client.get("/api/weeks")

    assert response.status_code == 200
    assert response.json() == [
        {
            "week_id": 202403,
            "week_start": "2024-01-15",
            "week_end": "2024-01-21",
            "doc_count": 12,
            "mention_count": 20,
            "skus_covered": ["ecoflow-delta2", "jackery-explorer-1000"],
        }
    ]


def test_overview_calculates_rates_and_scores(client: TestClient) -> None:
    response = client.get("/api/overview", params={"week_id": 202403})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total_mentions": 20,
        "sentiment_breakdown": {"positive": 10, "negative": 4, "neutral": 6},
    }
    assert body["top_aspects"][0]["positive_rate"] == 0.7
    assert body["sku_rankings"][0]["sentiment_score"] == 0.5


def test_overview_returns_404_for_missing_week(client: TestClient) -> None:
    response = client.get("/api/overview", params={"week_id": 202399})

    assert response.status_code == 404
    assert "202399" in response.json()["detail"]


def test_sku_list_and_detail_use_dashboard_scoped_aggregates(
    client: TestClient,
) -> None:
    list_response = client.get("/api/skus")
    detail_response = client.get("/api/skus/ecoflow-delta2", params={"week_id": 202403})

    assert list_response.status_code == 200
    assert list_response.json()[0]["dashboard_enabled"] is True
    assert detail_response.status_code == 200
    assert detail_response.json()["review_count"] == 12
    assert detail_response.json()["sentiment_breakdown"]["positive"] == 10
    assert detail_response.json()["top_aspects"][0]["positive_rate"] == 0.7


def test_sku_evidence_reuses_the_citation_provenance_contract(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/skus/ecoflow-delta2/evidence",
        params={"week_id": 202403, "sentiment": "positive"},
    )

    assert response.status_code == 200
    citation = response.json()[0]
    assert citation["evidence_preview"] == "It lasted through the whole weekend."
    assert citation["document_id"] == citation["source"]["document_id"]
    assert citation["sku_code"] == citation["source"]["sku_code"]


def test_sku_detail_and_evidence_reject_invalid_scopes(client: TestClient) -> None:
    missing_sku = client.get("/api/skus/not-a-sku", params={"week_id": 202403})
    missing_week = client.get(
        "/api/skus/ecoflow-delta2/evidence",
        params={"week_id": 202499, "sentiment": "positive"},
    )

    assert missing_sku.status_code == 400
    assert missing_week.status_code == 404


def test_compare_returns_authoritative_metrics_for_same_tier(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/compare",
        params=[
            ("sku_code", "ecoflow-delta2"),
            ("sku_code", "jackery-explorer-1000"),
            ("week_id", "202403"),
        ],
    )

    assert response.status_code == 200
    assert response.json()["capacity_tier"] == "mid"
    assert response.json()["skus"][0]["positive_rate"] == 0.6
    assert response.json()["skus"][0]["sentiment_score"] == 0.4


def test_compare_rejects_cross_tier_requests_with_structured_error(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/compare",
        params=[
            ("sku_code", "ecoflow-delta2"),
            ("sku_code", "anker-solix-f2000"),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "capacity_tier_mismatch"


def test_compare_rejects_invalid_iso_week_with_structured_error(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/compare",
        params=[
            ("sku_code", "ecoflow-delta2"),
            ("sku_code", "jackery-explorer-1000"),
            ("week_id", "202453"),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_week_range"


def test_report_retrieval_uses_existing_read_only_service(client: TestClient) -> None:
    response = client.get("/api/reports/202403", params={"sku_code": "ecoflow-delta2"})

    assert response.status_code == 200
    assert response.json()["summary"] == "Stored summary"


@pytest.mark.parametrize(
    ("week_id", "expected_status"),
    [(202453, 400), (202404, 404)],
)
def test_report_retrieval_validates_iso_week_and_missing_report(
    client: TestClient, week_id: int, expected_status: int
) -> None:
    response = client.get(
        f"/api/reports/{week_id}", params={"sku_code": "ecoflow-delta2"}
    )

    assert response.status_code == expected_status


def test_trends_limits_weeks_and_returns_locked_sku_metadata(
    client: TestClient, repository: FakeAspectRepository
) -> None:
    response = client.get("/api/skus/ecoflow-delta2/trends", params={"weeks": 2})

    assert response.status_code == 200
    assert repository.requested_trend_weeks == [202403, 202402]
    assert response.json() == {
        "sku_code": "ecoflow-delta2",
        "sku_name": "EcoFlow DELTA 2",
        "capacity_tier": "mid",
        "trends": [
            {
                "week_id": 202403,
                "aspect_label": "battery_capacity",
                "positive_count": 7,
                "negative_count": 2,
                "neutral_count": 1,
                "avg_quality_score": 0.74,
            }
        ],
    }


@pytest.mark.parametrize(
    ("path", "expected_text"),
    [
        ("/api/skus/not-a-sku/trends", "Valid options"),
        ("/api/skus/anker-solix-c300/trends", "disabled"),
        ("/api/skus/ecoflow-delta2/trends?weeks=13", "maximum: 12"),
    ],
)
def test_trends_returns_400_for_bad_requests(
    client: TestClient, path: str, expected_text: str
) -> None:
    response = client.get(path)

    assert response.status_code == 400
    assert expected_text in response.json()["detail"]


def test_database_failure_returns_retryable_503(
    client: TestClient, repository: FakeAspectRepository, monkeypatch
) -> None:
    async def fail_query():
        raise OperationalError("SELECT", {}, RuntimeError("db offline"))

    monkeypatch.setattr(repository, "get_week_aggregations", fail_query)

    response = client.get("/api/weeks")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert "retry" in response.json()["detail"]
