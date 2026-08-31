from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from backend.app.agent.schemas import RagToolArguments, ToolStatus, WeekRange
from backend.app.agent.tool_rag import RagRetrievalService, build_answer_citations
from backend.app.core.settings import settings
from backend.app.db.repositories.evidence_repo import EvidenceRepository
from backend.app.db.repositories.schemas import RetrievedEvidenceRow, SkuMetadata
from pipelines.embedding.milvus_repo import SearchResult


def sku(code: str) -> SkuMetadata:
    return SkuMetadata(
        sku_code=code,
        brand=code.split("-")[0].title(),
        model=code,
        capacity_wh=None,
        capacity_tier="mid",
        is_competitor=True,
        dashboard_enabled=True,
    )


def evidence_pair(
    *,
    sku_code: str = "ecoflow-delta2",
    aspect_label: str = "noise_level",
    sentiment: str = "negative",
    week_id: int = 202312,
    quality_score: float = 0.82,
    mention_text: str = "fan is extremely loud",
    score: float = 0.91,
) -> tuple[SearchResult, RetrievedEvidenceRow]:
    mention_id = uuid4()
    document_id = uuid4()
    hit = SearchResult(
        id=mention_id,
        score=score,
        metadata={
            "sku_code": sku_code,
            "aspect_label": aspect_label,
            "sentiment": sentiment,
            "week_id": week_id,
            "quality_score": quality_score,
        },
    )
    row = RetrievedEvidenceRow(
        mention_id=mention_id,
        document_id=document_id,
        sku_code=sku_code,
        aspect_label=aspect_label,
        sentiment=sentiment,
        mention_text=mention_text,
        context_window=f"The review says the {mention_text} during charging.",
        quality_score=quality_score,
        week_id=week_id,
        platform="amazon",
        published_at=datetime(2023, 3, 20),
        source_url="https://example.test/review/1",
        title="Verified review",
        rating=2,
        review_text=f"I used it overnight and the {mention_text} during charging.",
    )
    return hit, row


class FakeEvidenceRepository:
    def __init__(self, rows: list[RetrievedEvidenceRow]) -> None:
        self.rows = {row.mention_id: row for row in rows}
        self.enabled = [
            sku("ecoflow-delta2"),
            sku("jackery-explorer-1000"),
            sku("anker-solix-f2000"),
        ]
        self.hydration_calls: list[tuple[list[UUID], float]] = []

    async def get_enabled_skus(self) -> list[SkuMetadata]:
        return self.enabled

    async def hydrate_mentions(
        self, mention_ids: list[UUID], *, quality_threshold: float
    ) -> list[RetrievedEvidenceRow]:
        self.hydration_calls.append((mention_ids, quality_threshold))
        return [self.rows[item] for item in mention_ids if item in self.rows]


class FakeEmbedder:
    def __init__(self) -> None:
        self.texts: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts.append(texts)
        return [[0.1, 0.2]]


class TimeoutEmbedder(FakeEmbedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts.append(texts)
        raise TimeoutError("provider timeout")


class FakeMilvusRepository:
    def __init__(self, hits_by_sku: dict[str, list[SearchResult]]) -> None:
        self.hits_by_sku = hits_by_sku
        self.calls: list[dict[str, Any]] = []

    def search(self, query_vector: list[float], **kwargs: Any) -> list[SearchResult]:
        self.calls.append({"query_vector": query_vector, **kwargs})
        return self.hits_by_sku.get(kwargs["sku_code"], [])


def service_for(
    pairs: list[tuple[SearchResult, RetrievedEvidenceRow]],
    *,
    max_top_k: int = 20,
    quality_threshold: float = settings.aspect_quality_threshold,
    embedder: FakeEmbedder | None = None,
) -> tuple[
    RagRetrievalService,
    FakeEvidenceRepository,
    FakeEmbedder,
    FakeMilvusRepository,
]:
    hits_by_sku: dict[str, list[SearchResult]] = {}
    for hit, row in pairs:
        hits_by_sku.setdefault(row.sku_code, []).append(hit)
    repository = FakeEvidenceRepository([row for _, row in pairs])
    embedder = embedder or FakeEmbedder()
    milvus = FakeMilvusRepository(hits_by_sku)
    return (
        RagRetrievalService(
            repository,
            embedder,
            milvus,
            max_top_k=max_top_k,
            quality_threshold=quality_threshold,
        ),
        repository,
        embedder,
        milvus,
    )


@pytest.mark.asyncio
async def test_delta2_noise_returns_exact_traceable_evidence() -> None:
    hit, row = evidence_pair()
    service, _, embedder, _ = service_for([(hit, row)])

    result = await service.execute(
        RagToolArguments(query="How do users describe the noise?", sku_codes=[row.sku_code])
    )

    assert result.status is ToolStatus.SUCCESS
    assert result.payload is not None
    assert embedder.texts == [["How do users describe the noise?"]]
    evidence = result.payload.evidence[0]
    assert evidence.mention_id == hit.id == row.mention_id
    assert evidence.mention_text == "fan is extremely loud"
    assert evidence.mention_text in evidence.source.review_text


@pytest.mark.asyncio
async def test_negative_charging_query_is_semantic_and_filterable() -> None:
    hit, row = evidence_pair(
        aspect_label="charging_speed",
        sentiment="negative",
        mention_text="takes forever to charge",
    )
    service, _, _, milvus = service_for([(hit, row)])

    result = await service.execute(
        RagToolArguments(
            query="negative charging experiences",
            sku_codes=[row.sku_code],
            sentiment="negative",
        )
    )

    assert result.status is ToolStatus.SUCCESS
    assert milvus.calls[0]["sentiment"] == "negative"


@pytest.mark.asyncio
async def test_jackery_complaint_uses_requested_partition() -> None:
    hit, row = evidence_pair(sku_code="jackery-explorer-1000")
    service, _, _, milvus = service_for([(hit, row)])

    result = await service.execute(
        RagToolArguments(query="specific customer complaint", sku_codes=[row.sku_code])
    )

    assert result.status is ToolStatus.SUCCESS
    assert [call["sku_code"] for call in milvus.calls] == ["jackery-explorer-1000"]


@pytest.mark.asyncio
async def test_multi_sku_search_merges_by_score_and_applies_global_top_k() -> None:
    delta = evidence_pair(score=0.7)
    jackery = evidence_pair(sku_code="jackery-explorer-1000", score=0.9)
    service, _, _, milvus = service_for([delta, jackery])

    result = await service.execute(
        RagToolArguments(
            query="fan complaints",
            sku_codes=["ecoflow-delta2", "jackery-explorer-1000"],
            top_k=1,
        )
    )

    assert result.payload is not None
    assert result.payload.evidence[0].sku_code == "jackery-explorer-1000"
    assert len(milvus.calls) == 2


@pytest.mark.asyncio
async def test_sentiment_filter_is_passed_to_milvus() -> None:
    pair = evidence_pair(sentiment="negative")
    service, _, _, milvus = service_for([pair])
    await service.execute(
        RagToolArguments(
            query="complaints", sku_codes=["ecoflow-delta2"], sentiment="negative"
        )
    )

    assert milvus.calls[0]["sentiment"] == "negative"


@pytest.mark.asyncio
async def test_aspect_filter_is_validated_and_passed_to_milvus() -> None:
    pair = evidence_pair(aspect_label="noise_level")
    service, _, _, milvus = service_for([pair])
    result = await service.execute(
        RagToolArguments(
            query="fan", sku_codes=["ecoflow-delta2"], aspect_label="noise_level"
        )
    )

    assert result.status is ToolStatus.SUCCESS
    assert milvus.calls[0]["aspect_label"] == "noise_level"


@pytest.mark.asyncio
async def test_week_filter_is_passed_as_inclusive_milvus_range() -> None:
    pair = evidence_pair(week_id=202312)
    service, _, _, milvus = service_for([pair])
    result = await service.execute(
        RagToolArguments(
            query="noise",
            sku_codes=["ecoflow-delta2"],
            week_range=WeekRange(start_week_id=202312, end_week_id=202312),
        )
    )

    assert result.status is ToolStatus.SUCCESS
    assert milvus.calls[0]["week_id_range"] == (202312, 202312)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pair_kwargs", "argument_kwargs"),
    [
        ({"aspect_label": "charging_speed"}, {"aspect_label": "noise_level"}),
        ({"sentiment": "positive"}, {"sentiment": "negative"}),
        (
            {"week_id": 202312},
            {"week_range": WeekRange(start_week_id=202313, end_week_id=202313)},
        ),
    ],
)
async def test_hydrated_evidence_cannot_bypass_requested_filters(
    pair_kwargs: dict[str, object], argument_kwargs: dict[str, object]
) -> None:
    pair = evidence_pair(**pair_kwargs)
    service, _, _, _ = service_for([pair])
    result = await service.execute(
        RagToolArguments(
            query="filtered evidence",
            sku_codes=["ecoflow-delta2"],
            **argument_kwargs,
        )
    )

    assert result.status is ToolStatus.EMPTY
    assert result.payload is None
    assert [warning.code for warning in result.warnings] == ["filter_mismatch"]


@pytest.mark.asyncio
async def test_invalid_iso_week_is_rejected_before_external_calls() -> None:
    service, _, embedder, _ = service_for([])
    result = await service.execute(
        RagToolArguments(
            query="noise",
            sku_codes=["ecoflow-delta2"],
            week_range=WeekRange(start_week_id=202399, end_week_id=202399),
        )
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "invalid_week_range"
    assert embedder.texts == []


def test_invalid_sentiment_is_rejected_by_structured_arguments() -> None:
    with pytest.raises(ValidationError):
        RagToolArguments.model_validate(
            {
                "query": "charging",
                "sku_codes": ["ecoflow-delta2"],
                "sentiment": "angry",
            }
        )


@pytest.mark.asyncio
async def test_no_result_returns_structured_empty_without_hydration() -> None:
    service, repository, _, _ = service_for([])
    result = await service.execute(
        RagToolArguments(query="unsupported claim", sku_codes=["ecoflow-delta2"])
    )

    assert result.status is ToolStatus.EMPTY
    assert result.payload is None
    assert repository.hydration_calls == []


@pytest.mark.asyncio
async def test_embedding_timeout_returns_safe_retryable_error() -> None:
    embedder = TimeoutEmbedder()
    service, _, returned_embedder, _ = service_for([], embedder=embedder)

    result = await service.execute(
        RagToolArguments(query="noise", sku_codes=["ecoflow-delta2"])
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "rag_embedding_timeout"
    assert result.error.retryable is True
    assert "provider timeout" not in result.error.message
    assert returned_embedder.texts == [["noise"]]


@pytest.mark.asyncio
async def test_invalid_sku_is_rejected_before_embedding() -> None:
    service, _, embedder, _ = service_for([])
    result = await service.execute(
        RagToolArguments(query="noise", sku_codes=["not-a-locked-sku"])
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "unknown_or_disabled_sku"
    assert embedder.texts == []


@pytest.mark.asyncio
async def test_excessive_top_k_is_rejected_before_external_calls() -> None:
    service, repository, embedder, _ = service_for([], max_top_k=5)
    result = await service.execute(
        RagToolArguments(query="noise", sku_codes=["ecoflow-delta2"], top_k=6)
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "top_k_exceeds_limit"
    assert embedder.texts == []
    assert repository.hydration_calls == []


@pytest.mark.asyncio
async def test_invalid_aspect_is_rejected_against_enrichment_taxonomy() -> None:
    service, _, embedder, _ = service_for([])
    result = await service.execute(
        RagToolArguments(
            query="noise",
            sku_codes=["ecoflow-delta2"],
            aspect_label="made_up_aspect",
        )
    )

    assert result.status is ToolStatus.ERROR
    assert result.error is not None
    assert result.error.code == "invalid_aspect"
    assert embedder.texts == []


@pytest.mark.asyncio
async def test_source_document_hydration_retains_expandable_review_detail() -> None:
    pair = evidence_pair()
    service, _, _, _ = service_for([pair])
    result = await service.execute(
        RagToolArguments(query="noise", sku_codes=["ecoflow-delta2"])
    )

    assert result.payload is not None
    source = result.payload.evidence[0].source
    assert source.document_id == pair[1].document_id
    assert source.platform == "amazon"
    assert source.published_at == datetime(2023, 3, 20)
    assert source.review_text == pair[1].review_text


@pytest.mark.asyncio
async def test_quality_threshold_is_enforced_in_milvus_and_hydration() -> None:
    pair = evidence_pair(quality_score=0.77)
    service, repository, _, milvus = service_for(
        [pair], quality_threshold=0.77
    )
    result = await service.execute(
        RagToolArguments(query="noise", sku_codes=["ecoflow-delta2"])
    )

    assert result.status is ToolStatus.SUCCESS
    assert milvus.calls[0]["quality_threshold"] == 0.77
    assert repository.hydration_calls[0][1] == 0.77


@pytest.mark.asyncio
async def test_provenance_mismatch_is_excluded_as_partial_result() -> None:
    valid = evidence_pair(score=0.9)
    invalid = evidence_pair(score=0.8)
    invalid[0].metadata["week_id"] = 202401
    service, _, _, _ = service_for([valid, invalid])
    result = await service.execute(
        RagToolArguments(query="noise", sku_codes=["ecoflow-delta2"], top_k=2)
    )

    assert result.status is ToolStatus.PARTIAL
    assert result.payload is not None
    assert [item.mention_id for item in result.payload.evidence] == [valid[0].id]
    assert result.warnings[0].code == "provenance_mismatch"


@pytest.mark.asyncio
async def test_final_citations_can_select_three_of_eight_retrieved_items() -> None:
    pairs = [evidence_pair(score=0.99 - index / 100) for index in range(8)]
    service, _, _, _ = service_for(pairs)
    result = await service.execute(
        RagToolArguments(query="noise", sku_codes=["ecoflow-delta2"], top_k=8)
    )

    assert result.payload is not None
    selected_ids = [
        result.payload.evidence[index].mention_id for index in (0, 3, 7)
    ]
    citations = build_answer_citations(result.payload.evidence, selected_ids)
    assert [citation.mention_id for citation in citations] == selected_ids
    assert len(citations) == 3


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
async def test_hydration_query_rechecks_quality_dashboard_and_source_join() -> None:
    session = CapturingSession()
    await EvidenceRepository(session).hydrate_mentions([uuid4()])

    sql = str(session.statement)
    assert "aspect_mentions.quality_score >=" in sql
    assert "skus.dashboard_enabled IS true" in sql
    assert "documents" in sql
    assert settings.aspect_quality_threshold in session.statement.compile().params.values()
