import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.agent.llm import ModelResponse
from backend.app.agent.schemas import ReportToolArguments, ToolStatus
from backend.app.agent.tool_report import ReportService
from backend.app.api.reports import stream_report_events
from backend.app.db.repositories.schemas import SkuMetadata, WeeklyReportRow
from backend.app.reporting.service import (
    GenerateReportArguments,
    ReportGenerationFailure,
    ReportGenerationService,
)


def _sku() -> SkuMetadata:
    return SkuMetadata(
        sku_code="ecoflow-delta2",
        brand="EcoFlow",
        model="DELTA 2",
        capacity_wh=1024,
        capacity_tier="mid",
        is_competitor=False,
        dashboard_enabled=True,
    )


def _candidate_json() -> str:
    return json.dumps(
        {
            "summary": "Customer feedback was mostly positive, with a bounded charging concern.",
            "report_md": "\n".join(
                [
                    "## Executive Summary\nWeekly feedback is summarized from supplied VOC facts.",
                    "## Key Metrics\nThe deterministic counts are reflected above.",
                    "## Positive Themes\nBattery capacity was a positive theme.",
                    "## Negative Themes\nCharging was a reported limitation.",
                    "## SKU Highlights\nThis report is scoped to EcoFlow DELTA 2.",
                    "## Competitor Observations\nNo comparison data was supplied for this report.",
                ]
            ),
        }
    )


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, str | int]] = []
        self.current: WeeklyReportRow | None = None

    async def get_enabled_skus(self):
        return [_sku()]

    async def save_weekly_report(self, **kwargs):
        self.saved.append(kwargs)
        self.current = WeeklyReportRow(
            report_id=uuid4(),
            sku_code=kwargs["sku_code"],
            week_id=kwargs["week_id"],
            report_md=kwargs["report_md"],
            summary=kwargs["summary"],
            generated_at=datetime(2026, 9, 11, tzinfo=UTC),
        )
        return self.current

    async def get_weekly_report(self, *, sku_code: str, week_id: int):
        if (
            self.current is not None
            and self.current.sku_code == sku_code
            and self.current.week_id == week_id
        ):
            return self.current
        return None


class FakeAnalytics:
    def __init__(self, status=ToolStatus.SUCCESS) -> None:
        self.status = status

    async def execute(self, arguments):
        if self.status is not ToolStatus.SUCCESS:
            return SimpleNamespace(
                status=self.status, payload=None, error=None, warnings=[]
            )
        payloads = {
            "review_count": {"review_count": 12, "mention_count": 20, "by_sku": []},
            "sentiment_distribution": {"mention_count": 20, "distribution": []},
            "aspect_distribution": {"mention_count": 20, "distribution": []},
        }
        return SimpleNamespace(
            status=ToolStatus.SUCCESS,
            payload=SimpleNamespace(model_dump=lambda mode: payloads[arguments.operation.value]),
            error=None,
            warnings=[],
        )


class FakeRag:
    async def execute(self, arguments):
        evidence = [
            SimpleNamespace(
                aspect_label="battery_capacity",
                sentiment=arguments.sentiment,
                mention_text="It lasted through the weekend.",
            )
        ]
        return SimpleNamespace(
            status=ToolStatus.SUCCESS,
            payload=SimpleNamespace(evidence=evidence),
            error=None,
        )


class FakeModel:
    def __init__(self, content: str | None = None) -> None:
        self.content = content or _candidate_json()
        self.requests = []

    async def complete(self, **kwargs):
        self.requests.append(kwargs)
        return ModelResponse(content=self.content)


def _service(*, analytics=None, model=None, repository=None):
    return ReportGenerationService(
        repository or FakeRepository(), analytics or FakeAnalytics(), FakeRag(), model or FakeModel()
    )


class FakeRequest:
    async def is_disconnected(self):
        return False


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


async def _stream_event_types(**kwargs):
    records = [record async for record in stream_report_events(**kwargs)]
    return [record.split("\n")[0].removeprefix("event: ") for record in records]


@pytest.mark.asyncio
async def test_generation_collects_deterministic_facts_validates_candidate_and_stages_save():
    repository = FakeRepository()
    model = FakeModel()
    service = _service(repository=repository, model=model)
    arguments = GenerateReportArguments(sku_code="ecoflow-delta2", week_id=202635)

    facts = await service.collect_analytics(arguments)
    facts = await service.retrieve_evidence(facts)
    candidate = await service.synthesize(facts)
    report = await service.persist(arguments, candidate)

    assert facts["metrics"]["review_count"]["review_count"] == 12
    assert len(facts["evidence"]) == 2
    assert "Evidence/Citations" not in candidate.report_md
    assert report.sku_code == "ecoflow-delta2"
    assert repository.saved[0]["summary"] == candidate.summary
    assert model.requests[0]["tools"] == []


@pytest.mark.asyncio
async def test_no_data_refuses_generation_before_evidence_or_persistence():
    repository = FakeRepository()
    service = _service(repository=repository, analytics=FakeAnalytics(ToolStatus.EMPTY))

    with pytest.raises(ReportGenerationFailure) as exc:
        await service.collect_analytics(
            GenerateReportArguments(sku_code="ecoflow-delta2", week_id=202635)
        )

    assert exc.value.error.code == "report_not_possible"
    assert repository.saved == []


@pytest.mark.asyncio
async def test_invalid_model_candidate_is_not_persisted():
    repository = FakeRepository()
    service = _service(
        repository=repository,
        model=FakeModel('{"report_md":"too short","summary":"too short"}'),
    )
    arguments = GenerateReportArguments(sku_code="ecoflow-delta2", week_id=202635)
    facts = await service.collect_analytics(arguments)
    facts = await service.retrieve_evidence(facts)

    with pytest.raises(ReportGenerationFailure) as exc:
        await service.synthesize(facts)

    assert exc.value.error.code == "report_validation_failed"
    assert repository.saved == []


@pytest.mark.asyncio
async def test_successful_regeneration_replaces_the_readable_report_only_after_candidate_validation():
    repository = FakeRepository()
    repository.current = WeeklyReportRow(
        report_id=uuid4(),
        sku_code="ecoflow-delta2",
        week_id=202635,
        report_md="# Previous report",
        summary="Previous summary remains until replacement succeeds.",
        generated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    service = _service(repository=repository)
    arguments = GenerateReportArguments(sku_code="ecoflow-delta2", week_id=202635)
    facts = await service.retrieve_evidence(await service.collect_analytics(arguments))
    candidate = await service.synthesize(facts)

    await service.persist(arguments, candidate)
    read_back = await ReportService(repository).execute(
        ReportToolArguments(sku_code="ecoflow-delta2", week_id=202635)
    )

    assert len(repository.saved) == 1
    assert read_back.payload is not None
    assert read_back.payload.report_md == candidate.report_md


@pytest.mark.asyncio
async def test_invalid_scope_is_rejected_before_analytics():
    service = _service()

    with pytest.raises(ReportGenerationFailure) as exc:
        await service.collect_analytics(
            GenerateReportArguments(sku_code="not-a-sku", week_id=202635)
        )

    assert exc.value.error.code == "unknown_or_disabled_sku"


@pytest.mark.asyncio
async def test_stream_commits_before_terminal_completed_event():
    transaction = FakeTransaction()
    events = await _stream_event_types(
        payload=GenerateReportArguments(sku_code="ecoflow-delta2", week_id=202635),
        service=_service(),
        request=FakeRequest(),
        transaction=transaction,
    )

    assert events == [
        "report_started",
        "stage_started",
        "stage_completed",
        "stage_started",
        "stage_completed",
        "stage_started",
        "stage_completed",
        "stage_started",
        "stage_completed",
        "report_delta",
        "report_delta",
        "stage_started",
        "stage_completed",
        "report_completed",
    ]
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


@pytest.mark.asyncio
async def test_stream_validation_failure_is_terminal_and_never_commits():
    transaction = FakeTransaction()
    events = await _stream_event_types(
        payload=GenerateReportArguments(sku_code="ecoflow-delta2", week_id=202635),
        service=_service(model=FakeModel('{"report_md":"bad","summary":"bad"}')),
        request=FakeRequest(),
        transaction=transaction,
    )

    assert events[-1] == "error"
    assert "report_completed" not in events
    assert transaction.commits == 0
    assert transaction.rollbacks == 1
