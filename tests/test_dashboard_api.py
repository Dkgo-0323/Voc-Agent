from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app.api.dashboard import get_aspect_repository
from backend.app.db.repositories.schemas import (
    SkuMetadata,
    SkuRanking,
    SkuTrend,
    TopAspect,
    WeekAggregation,
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


@pytest.fixture
def repository() -> FakeAspectRepository:
    return FakeAspectRepository()


@pytest.fixture
def client(repository: FakeAspectRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_aspect_repository] = lambda: repository
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
