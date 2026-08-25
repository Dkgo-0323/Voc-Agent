"""Scheduled orchestration for the weekly enrichment and embedding pipeline."""

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI

from backend.app.core.database import get_db_context
from backend.app.core.settings import settings
from backend.app.db.repositories.aspect_repo import AspectRepository
from backend.app.db.repositories.document_repo import DocumentRepository
from backend.app.db.repositories.schemas import (
    AspectMentionCreate,
    AspectMentionRead,
    DocumentRead,
)
from pipelines.embedding.embedder import Embedder, EmbeddingInput, build_embed_text
from pipelines.embedding.milvus_repo import MilvusRecord, MilvusRepository
from pipelines.enrichment.aspect_extractor import (
    MAX_BATCH_SIZE,
    AspectExtractor,
    BatchExtractionResult,
    ExtractionResponseError,
    build_aspect_mentions,
    prepare_document,
)

logger = logging.getLogger(__name__)

DEFAULT_DOCUMENT_LIMIT = 500
MAX_EXTRACTION_CONCURRENCY = 3
MAX_ERROR_LENGTH = 4000


@dataclass
class PipelineRunStats:
    """Serializable metrics for one scheduler invocation."""

    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    raw_documents_fetched: int = 0
    documents_filtered: int = 0
    documents_enriched: int = 0
    mentions_inserted: int = 0
    documents_embedded: int = 0
    vectors_upserted: int = 0
    documents_failed: int = 0
    embedding_deferred: int = 0
    duration_seconds: float = 0.0
    stage_seconds: dict[str, float] = field(default_factory=dict)


def _structured_log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def _batches(
    items: Sequence[DocumentRead], size: int = MAX_BATCH_SIZE
) -> list[list[DocumentRead]]:
    return [
        list(items[offset : offset + size]) for offset in range(0, len(items), size)
    ]


def _error_message(error: BaseException) -> str:
    message = f"{type(error).__name__}: {error}"
    return message[:MAX_ERROR_LENGTH]


def _processing_error_message(error: BaseException) -> str:
    """Include invalid model output in PostgreSQL, but never in structured logs."""
    message = _error_message(error)
    raw_response = getattr(error, "raw_response", None)
    if raw_response:
        message += f"\nLLM response: {raw_response}"
    return message[:MAX_ERROR_LENGTH]


def _normalized_base_url(value: str) -> str:
    return value.rstrip("/").lower()


def _resolve_llm_api_key() -> str:
    """Resolve a key without accidentally sending it to a different provider."""
    if settings.llm_api_key:
        return settings.llm_api_key
    if _normalized_base_url(settings.llm_base_url) == _normalized_base_url(
        settings.embedding_base_url
    ):
        return settings.embedding_api_key
    if "api.openai.com" in settings.llm_base_url:
        return settings.openai_api_key
    return ""


def build_aspect_extractor(
    *, timeout_seconds: float | None = None, max_retries: int | None = None
) -> AspectExtractor:
    """Build the configured OpenAI-compatible enrichment client."""
    api_key = _resolve_llm_api_key()
    if not api_key:
        raise ValueError(
            "LLM_API_KEY is not configured and no same-provider key can be reused"
        )
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.llm_base_url,
        timeout=timeout_seconds or settings.llm_timeout_seconds,
        max_retries=(settings.llm_max_retries if max_retries is None else max_retries),
    )
    return AspectExtractor(
        client,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        request_extra_body=settings.llm_extra_body,
    )


async def _fetch_documents(status: str, limit: int | None = None) -> list[DocumentRead]:
    async with get_db_context() as session:
        repository = DocumentRepository(session)
        if status == "raw" and limit is not None:
            return await repository.fetch_unprocessed(limit)
        return await repository.fetch_by_status(status)


async def _persist_enriched_document(
    document_id: UUID, mentions: Sequence[AspectMentionCreate]
) -> None:
    """Insert one document's mentions and advance its state in one transaction."""
    async with get_db_context() as session:
        aspect_repository = AspectRepository(session)
        document_repository = DocumentRepository(session)
        inserted_ids = await aspect_repository.bulk_insert(mentions)
        if len(inserted_ids) != len(mentions):
            raise RuntimeError("Not all aspect mentions were inserted")
        if not await document_repository.update_status(document_id, "enriched"):
            raise RuntimeError(f"Document {document_id} no longer exists")


async def _mark_failed(document_id: UUID, error: BaseException) -> None:
    async with get_db_context() as session:
        updated = await DocumentRepository(session).update_status(
            document_id, "failed", _processing_error_message(error)
        )
        if not updated:
            raise RuntimeError(f"Document {document_id} no longer exists")


async def _fetch_mentions(document_ids: Sequence[UUID]) -> list[AspectMentionRead]:
    async with get_db_context() as session:
        return await AspectRepository(session).fetch_by_document_ids(document_ids)


async def _mark_documents_embedded(
    document_ids: Sequence[UUID], embed_text_by_id: dict[UUID, str] | None = None
) -> None:
    if not document_ids:
        return
    async with get_db_context() as session:
        aspect_repository = AspectRepository(session)
        document_repository = DocumentRepository(session)
        if embed_text_by_id:
            updated_mentions = await aspect_repository.bulk_update_embed_text(
                embed_text_by_id
            )
            if updated_mentions != len(embed_text_by_id):
                raise RuntimeError("Not all embedding texts were persisted")
        updated_documents = await document_repository.bulk_update_status(
            list(document_ids), "embedded"
        )
        if updated_documents != len(document_ids):
            raise RuntimeError("Not all documents were marked embedded")


async def _extract_batch(
    extractor: AspectExtractor,
    batch: list[DocumentRead],
    semaphore: asyncio.Semaphore,
) -> tuple[list[DocumentRead], BatchExtractionResult | BaseException]:
    try:
        async with semaphore:
            return batch, await extractor.extract(batch)
    except Exception as error:
        return batch, error


async def _run_enrichment_stage(
    documents: Sequence[DocumentRead],
    extractor: AspectExtractor | None,
    stats: PipelineRunStats,
) -> None:
    eligible: list[DocumentRead] = []
    filtered: list[DocumentRead] = []
    for document in documents:
        if prepare_document(document) is None:
            filtered.append(document)
        else:
            eligible.append(document)
    stats.documents_filtered = len(filtered)

    # Noise is a successful terminal enrichment result with zero mentions. Moving it
    # through enriched lets Stage 3 mark it embedded and prevents endless re-filtering.
    for document in filtered:
        try:
            await _persist_enriched_document(document.id, [])
            stats.documents_enriched += 1
        except Exception as error:
            stats.documents_failed += 1
            _structured_log(
                "document_enrichment_persist_failed",
                document_id=document.id,
                error=_error_message(error),
            )

    if not eligible:
        return
    if extractor is None:
        extractor = build_aspect_extractor()

    semaphore = asyncio.Semaphore(MAX_EXTRACTION_CONCURRENCY)
    results = await asyncio.gather(
        *(_extract_batch(extractor, batch, semaphore) for batch in _batches(eligible))
    )
    for batch, result in results:
        if isinstance(result, BaseException):
            for document in batch:
                try:
                    await _mark_failed(document.id, result)
                except Exception as status_error:
                    _structured_log(
                        "document_failure_status_update_failed",
                        document_id=document.id,
                        error=_error_message(status_error),
                    )
                stats.documents_failed += 1
            _structured_log(
                "extraction_batch_failed",
                document_ids=[str(document.id) for document in batch],
                error=_error_message(result),
            )
            continue

        mentions = build_aspect_mentions(batch, result)
        mentions_by_document: dict[UUID, list[AspectMentionCreate]] = {
            document.id: [] for document in batch
        }
        for mention in mentions:
            mentions_by_document[mention.document_id].append(mention)

        for document in batch:
            if validation_error := result.failed_document_errors.get(document.id):
                error = ExtractionResponseError(validation_error)
                try:
                    await _mark_failed(document.id, error)
                except Exception as status_error:
                    _structured_log(
                        "document_failure_status_update_failed",
                        document_id=document.id,
                        error=_error_message(status_error),
                    )
                stats.documents_failed += 1
                _structured_log(
                    "document_mentions_rejected",
                    document_id=document.id,
                    error=validation_error,
                )
                continue
            document_mentions = mentions_by_document[document.id]
            try:
                await _persist_enriched_document(document.id, document_mentions)
            except Exception as error:
                # The transaction rolls back both the mentions and status. The raw
                # document can be retried because no partial SQL state is visible.
                stats.documents_failed += 1
                _structured_log(
                    "document_enrichment_persist_failed",
                    document_id=document.id,
                    error=_error_message(error),
                )
                continue
            stats.documents_enriched += 1
            stats.mentions_inserted += len(document_mentions)


async def _run_embedding_stage(
    embedder: Embedder | None,
    milvus_repository: MilvusRepository,
    stats: PipelineRunStats,
    enriched_documents: Sequence[DocumentRead] | None = None,
) -> None:
    if enriched_documents is None:
        enriched_documents = await _fetch_documents("enriched")
    if not enriched_documents:
        return

    document_ids = [document.id for document in enriched_documents]
    mentions = await _fetch_mentions(document_ids)
    documents_with_mentions = {mention.document_id for mention in mentions}
    empty_document_ids = [
        document_id
        for document_id in document_ids
        if document_id not in documents_with_mentions
    ]
    await _mark_documents_embedded(empty_document_ids)
    stats.documents_embedded += len(empty_document_ids)

    if not mentions:
        return
    if embedder is None:
        embedder = Embedder()

    texts = [
        build_embed_text(
            EmbeddingInput(
                sku_name={
                    document.id: document.sku_name for document in enriched_documents
                }[mention.document_id],
                aspect_label=mention.aspect_label,
                mention_text=mention.mention_text,
                context_window=mention.context_window,
            )
        )
        for mention in mentions
    ]
    try:
        vectors = await embedder.embed(texts)
        if len(vectors) != len(mentions):
            raise RuntimeError("Embedding API returned an incomplete result")
        records = [
            MilvusRecord(
                id=mention.id,
                vector=vector,
                sku_code=mention.sku_code,
                aspect_label=mention.aspect_label,
                sentiment=mention.sentiment,
                week_id=mention.week_id,
                quality_score=mention.quality_score or 0.0,
            )
            for mention, vector in zip(mentions, vectors, strict=True)
        ]
        upserted = await asyncio.to_thread(milvus_repository.upsert_vectors, records)
        if upserted != len(records):
            raise RuntimeError("Milvus did not upsert every vector")

        await _mark_documents_embedded(
            list(documents_with_mentions),
            {mention.id: text for mention, text in zip(mentions, texts, strict=True)},
        )
    except Exception as error:
        # PostgreSQL remains enriched. A later run regenerates/upserts the same UUIDs,
        # so both a total failure and a partial Milvus write are safe to retry.
        stats.embedding_deferred += len(documents_with_mentions)
        _structured_log(
            "embedding_stage_deferred",
            document_count=len(documents_with_mentions),
            mention_count=len(mentions),
            error=_error_message(error),
        )
        return

    stats.vectors_upserted += upserted
    stats.documents_embedded += len(documents_with_mentions)


async def weekly_pipeline_job(
    *,
    document_limit: int = DEFAULT_DOCUMENT_LIMIT,
    extractor: AspectExtractor | None = None,
    embedder: Embedder | None = None,
    milvus_repository: MilvusRepository | None = None,
) -> PipelineRunStats:
    """Run Day 4's idempotent raw -> enriched -> embedded workflow."""
    if document_limit < 1:
        raise ValueError("document_limit must be positive")

    started = perf_counter()
    stats = PipelineRunStats()
    milvus_repository = milvus_repository or MilvusRepository()
    _structured_log("weekly_pipeline_started", document_limit=document_limit)

    stage_started = perf_counter()
    await asyncio.to_thread(milvus_repository.setup_collection)
    stats.stage_seconds["precheck"] = round(perf_counter() - stage_started, 4)

    stage_started = perf_counter()
    raw_documents = await _fetch_documents("raw", document_limit)
    stats.raw_documents_fetched = len(raw_documents)
    stats.stage_seconds["fetch"] = round(perf_counter() - stage_started, 4)
    _structured_log("raw_documents_fetched", count=len(raw_documents))

    if raw_documents:
        stage_started = perf_counter()
        await _run_enrichment_stage(raw_documents, extractor, stats)
        stats.stage_seconds["enrichment"] = round(perf_counter() - stage_started, 4)
        _structured_log(
            "enrichment_stage_completed",
            filtered=stats.documents_filtered,
            enriched=stats.documents_enriched,
            mentions=stats.mentions_inserted,
            failed=stats.documents_failed,
        )

    stage_started = perf_counter()
    await _run_embedding_stage(embedder, milvus_repository, stats)
    stats.stage_seconds["embedding"] = round(perf_counter() - stage_started, 4)

    stats.duration_seconds = round(perf_counter() - started, 4)
    _structured_log("weekly_pipeline_completed", **asdict(stats))
    return stats


async def run_enrichment_pipeline(**kwargs: Any) -> PipelineRunStats:
    """Backward-compatible entry point retained for existing worker callers."""
    return await weekly_pipeline_job(**kwargs)
