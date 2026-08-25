from datetime import datetime
from uuid import UUID, uuid4

import pytest

from backend.app.core.settings import settings
from backend.app.db.repositories.schemas import AspectMentionRead, DocumentRead
from backend.worker import jobs
from backend.worker.main import build_scheduler
from pipelines.enrichment.aspect_extractor import (
    BatchExtractionResult,
    ExtractedAspect,
    ExtractedDocument,
)


def make_document(status: str = "raw") -> DocumentRead:
    return DocumentRead(
        id=uuid4(),
        sku_id=uuid4(),
        sku_code="ecoflow-delta2",
        sku_name="EcoFlow DELTA 2",
        platform="amazon",
        external_id="worker-review-1",
        title=None,
        body="The battery is reliable and the fan is extremely loud at night.",
        rating=3,
        author_hash=None,
        source_url=None,
        published_at=None,
        week_id=202632,
        ingested_at=datetime.now(),
        processing_status=status,
        processing_error=None,
        processed_at=None,
    )


class FakeExtractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, documents):
        self.calls += 1
        return BatchExtractionResult(
            documents=[
                ExtractedDocument(
                    document_id=document.id,
                    aspects=[
                        ExtractedAspect(
                            aspect_label="noise_level",
                            sentiment="negative",
                            confidence=0.9,
                            mention_text="fan is extremely loud",
                            context_window=document.body,
                        )
                    ],
                )
                for document in documents
            ],
            skipped_document_ids=[],
        )


class FakeEmbedder:
    async def embed(self, texts):
        return [[0.0] * settings.embedding_dimensions for _ in texts]


class FakeMilvus:
    def __init__(self) -> None:
        self.setup_calls = 0
        self.upserted = []

    def setup_collection(self):
        self.setup_calls += 1

    def upsert_vectors(self, records):
        self.upserted.extend(records)
        return len(records)


@pytest.mark.asyncio
async def test_weekly_job_completes_and_is_idempotent(monkeypatch) -> None:
    document = make_document()
    state = {document.id: "raw"}
    stored_mentions: list[AspectMentionRead] = []
    persisted_embed_text: dict[UUID, str] = {}

    async def fetch_documents(status, limit=None):
        if state[document.id] != status:
            return []
        return [document.model_copy(update={"processing_status": status})]

    async def persist_enriched(document_id, mentions):
        for mention in mentions:
            stored_mentions.append(
                AspectMentionRead(
                    id=uuid4(),
                    created_at=datetime.now(),
                    **mention.model_dump(),
                )
            )
        state[document_id] = "enriched"

    async def fetch_mentions(document_ids):
        return [
            mention
            for mention in stored_mentions
            if mention.document_id in document_ids
        ]

    async def mark_embedded(document_ids, embed_text_by_id=None):
        persisted_embed_text.update(embed_text_by_id or {})
        for document_id in document_ids:
            state[document_id] = "embedded"

    monkeypatch.setattr(jobs, "_fetch_documents", fetch_documents)
    monkeypatch.setattr(jobs, "_persist_enriched_document", persist_enriched)
    monkeypatch.setattr(jobs, "_fetch_mentions", fetch_mentions)
    monkeypatch.setattr(jobs, "_mark_documents_embedded", mark_embedded)

    extractor = FakeExtractor()
    milvus = FakeMilvus()
    first = await jobs.weekly_pipeline_job(
        extractor=extractor,
        embedder=FakeEmbedder(),
        milvus_repository=milvus,
    )

    assert state[document.id] == "embedded"
    assert first.documents_enriched == 1
    assert first.mentions_inserted == 1
    assert first.documents_embedded == 1
    assert first.vectors_upserted == 1
    assert len(persisted_embed_text) == 1

    second = await jobs.weekly_pipeline_job(
        extractor=extractor,
        embedder=FakeEmbedder(),
        milvus_repository=milvus,
    )
    assert second.raw_documents_fetched == 0
    assert second.vectors_upserted == 0
    assert extractor.calls == 1
    assert len(milvus.upserted) == 1


@pytest.mark.asyncio
async def test_embedding_failure_keeps_document_enriched(monkeypatch) -> None:
    document = make_document(status="enriched")
    mention = AspectMentionRead(
        id=uuid4(),
        document_id=document.id,
        sku_code=document.sku_code,
        week_id=document.week_id,
        aspect_label="noise_level",
        sentiment="negative",
        sentiment_score=-1.0,
        confidence=0.9,
        mention_text="fan is extremely loud",
        context_window=document.body,
        quality_score=0.8,
        embed_text=None,
        created_at=datetime.now(),
    )
    marked: list[UUID] = []

    async def fetch_documents(status, limit=None):
        return [document] if status == "enriched" else []

    async def fetch_mentions(document_ids):
        return [mention]

    async def mark_embedded(document_ids, embed_text_by_id=None):
        marked.extend(document_ids)

    class FailingEmbedder:
        async def embed(self, texts):
            raise RuntimeError("temporary embedding outage")

    monkeypatch.setattr(jobs, "_fetch_documents", fetch_documents)
    monkeypatch.setattr(jobs, "_fetch_mentions", fetch_mentions)
    monkeypatch.setattr(jobs, "_mark_documents_embedded", mark_embedded)

    result = await jobs.weekly_pipeline_job(
        embedder=FailingEmbedder(), milvus_repository=FakeMilvus()
    )

    assert result.embedding_deferred == 1
    assert result.documents_embedded == 0
    assert marked == []


def test_scheduler_uses_weekly_single_instance_policy() -> None:
    job = build_scheduler().get_job("weekly_enrichment")

    assert job is not None
    assert job.max_instances == 1
    assert job.coalesce is True
    assert "day_of_week='sun'" in str(job.trigger)
    assert "hour='2'" in str(job.trigger)


def test_llm_key_reuses_embedding_key_only_for_same_provider(monkeypatch) -> None:
    monkeypatch.setattr(jobs.settings, "llm_api_key", "")
    monkeypatch.setattr(jobs.settings, "openai_api_key", "legacy-openai-key")
    monkeypatch.setattr(jobs.settings, "embedding_api_key", "zhipu-key")
    monkeypatch.setattr(
        jobs.settings, "llm_base_url", "https://open.bigmodel.cn/api/paas/v4/"
    )
    monkeypatch.setattr(
        jobs.settings, "embedding_base_url", "https://open.bigmodel.cn/api/paas/v4"
    )

    assert jobs._resolve_llm_api_key() == "zhipu-key"

    monkeypatch.setattr(
        jobs.settings,
        "llm_base_url",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    assert jobs._resolve_llm_api_key() == ""


@pytest.mark.asyncio
async def test_filtered_document_does_not_initialize_llm(monkeypatch) -> None:
    document = make_document().model_copy(update={"body": "too short"})
    state = {document.id: "raw"}

    async def fetch_documents(status, limit=None):
        if state[document.id] != status:
            return []
        return [document.model_copy(update={"processing_status": status})]

    async def persist_enriched(document_id, mentions):
        assert mentions == []
        state[document_id] = "enriched"

    async def fetch_mentions(document_ids):
        return []

    async def mark_embedded(document_ids, embed_text_by_id=None):
        for document_id in document_ids:
            state[document_id] = "embedded"

    def unexpected_llm_initialization():
        raise AssertionError("filtered documents must not initialize the LLM")

    monkeypatch.setattr(jobs, "_fetch_documents", fetch_documents)
    monkeypatch.setattr(jobs, "_persist_enriched_document", persist_enriched)
    monkeypatch.setattr(jobs, "_fetch_mentions", fetch_mentions)
    monkeypatch.setattr(jobs, "_mark_documents_embedded", mark_embedded)
    monkeypatch.setattr(jobs, "build_aspect_extractor", unexpected_llm_initialization)

    result = await jobs.weekly_pipeline_job(milvus_repository=FakeMilvus())

    assert state[document.id] == "embedded"
    assert result.documents_filtered == 1
    assert result.documents_embedded == 1


@pytest.mark.asyncio
async def test_invalid_document_isolated_from_valid_batch_peer(monkeypatch) -> None:
    invalid = make_document()
    valid = make_document().model_copy(
        update={"id": uuid4(), "external_id": "worker-review-2"}
    )
    persisted: list[UUID] = []
    failed: list[UUID] = []
    stored_mentions: list[AspectMentionRead] = []
    embedded: list[UUID] = []

    class PartiallyValidExtractor:
        async def extract(self, documents):
            return BatchExtractionResult(
                documents=[
                    ExtractedDocument(document_id=invalid.id, aspects=[]),
                    ExtractedDocument(
                        document_id=valid.id,
                        aspects=[
                            ExtractedAspect(
                                aspect_label="noise_level",
                                sentiment="negative",
                                confidence=0.9,
                                mention_text="fan is extremely loud",
                                context_window=valid.body,
                            )
                        ],
                    ),
                ],
                skipped_document_ids=[],
                failed_document_errors={
                    invalid.id: "All returned aspect mentions were invalid"
                },
            )

    async def persist_enriched(document_id, mentions):
        persisted.append(document_id)
        assert document_id == valid.id
        assert len(mentions) == 1
        stored_mentions.extend(
            AspectMentionRead(
                id=uuid4(), created_at=datetime.now(), **item.model_dump()
            )
            for item in mentions
        )

    async def mark_failed(document_id, error):
        failed.append(document_id)

    async def fetch_mentions(document_ids):
        return [
            mention
            for mention in stored_mentions
            if mention.document_id in document_ids
        ]

    async def mark_embedded(document_ids, embed_text_by_id=None):
        embedded.extend(document_ids)

    monkeypatch.setattr(jobs, "_persist_enriched_document", persist_enriched)
    monkeypatch.setattr(jobs, "_mark_failed", mark_failed)
    monkeypatch.setattr(jobs, "_fetch_mentions", fetch_mentions)
    monkeypatch.setattr(jobs, "_mark_documents_embedded", mark_embedded)
    stats = jobs.PipelineRunStats()

    await jobs._run_enrichment_stage([invalid, valid], PartiallyValidExtractor(), stats)
    milvus = FakeMilvus()
    await jobs._run_embedding_stage(
        FakeEmbedder(), milvus, stats, enriched_documents=[valid]
    )

    assert persisted == [valid.id]
    assert failed == [invalid.id]
    assert stats.documents_enriched == 1
    assert stats.documents_failed == 1
    assert stats.mentions_inserted == 1
    assert stats.documents_embedded == 1
    assert stats.vectors_upserted == 1
    assert embedded == [valid.id]
    assert len(milvus.upserted) == 1
