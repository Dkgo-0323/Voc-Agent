"""Run a bounded, explicit Week 2 E2E acceptance batch and audit its results.

The caller must supply one to five currently-raw document UUIDs.  This script never
selects arbitrary documents, never prints review bodies, and leaves unrelated raw
documents untouched.
"""

import argparse
import asyncio
import json
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select

from backend.app.core.database import close_db, get_db_context, init_db
from backend.app.db.models import AspectMention, Document, Sku
from backend.app.db.repositories.schemas import DocumentRead
from backend.worker.jobs import (
    PipelineRunStats,
    _run_embedding_stage,
    _run_enrichment_stage,
)
from pipelines.embedding.milvus_repo import MilvusRepository

MAX_ACCEPTANCE_DOCUMENTS = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--document-id",
        action="append",
        required=True,
        help="Raw document UUID to process; repeat at most five times.",
    )
    return parser.parse_args()


async def _load_selected_documents(document_ids: list[UUID]) -> list[DocumentRead]:
    async with get_db_context() as session:
        result = await session.execute(
            select(Document, Sku.sku_code, (Sku.brand + " " + Sku.model).label("sku_name"))
            .join(Sku, Document.sku_id == Sku.id)
            .where(Document.id.in_(document_ids))
        )
        documents = [
            DocumentRead.model_validate(
                {**document.__dict__, "sku_code": sku_code, "sku_name": sku_name}
            )
            for document, sku_code, sku_name in result
        ]
    by_id = {document.id: document for document in documents}
    missing = [str(document_id) for document_id in document_ids if document_id not in by_id]
    if missing:
        raise ValueError(f"Unknown document_id values: {missing}")
    ordered = [by_id[document_id] for document_id in document_ids]
    invalid = [
        {
            "document_id": str(document.id),
            "sku_code": document.sku_code,
            "status": document.processing_status,
        }
        for document in ordered
        if document.processing_status != "raw"
    ]
    if invalid:
        raise ValueError(f"Acceptance documents must all be raw: {invalid}")
    return ordered


async def _selected_enriched_documents(document_ids: list[UUID]) -> list[DocumentRead]:
    async with get_db_context() as session:
        result = await session.execute(
            select(Document, Sku.sku_code, (Sku.brand + " " + Sku.model).label("sku_name"))
            .join(Sku, Document.sku_id == Sku.id)
            .where(
                Document.id.in_(document_ids),
                Document.processing_status == "enriched",
            )
        )
        return [
            DocumentRead.model_validate(
                {**document.__dict__, "sku_code": sku_code, "sku_name": sku_name}
            )
            for document, sku_code, sku_name in result
        ]


async def _audit(document_ids: list[UUID], baseline_ids: set[UUID]) -> dict[str, object]:
    async with get_db_context() as session:
        document_rows = (
            await session.execute(
                select(Document, Sku.sku_code, (Sku.brand + " " + Sku.model).label("sku_name"))
                .join(Sku, Document.sku_id == Sku.id)
                .where(Document.id.in_(document_ids))
            )
        ).all()
        documents = {row[0].id: row for row in document_rows}
        mentions = (
            await session.execute(
                select(AspectMention).where(AspectMention.document_id.in_(document_ids))
            )
        ).scalars().all()

    new_mentions = [mention for mention in mentions if mention.id not in baseline_ids]
    invalid_excerpt_ids = [
        str(mention.id)
        for mention in new_mentions
        if mention.mention_text not in documents[mention.document_id][0].body
    ]
    invalid_quality_ids = [
        str(mention.id)
        for mention in new_mentions
        if mention.quality_score is None or not 0 <= mention.quality_score <= 1
    ]
    invalid_embed_text_ids = [
        str(mention.id)
        for mention in new_mentions
        if not mention.embed_text
        or not mention.embed_text.startswith(
            f"[{documents[mention.document_id][2]}] [{mention.aspect_label}]:"
        )
    ]
    failed_document_ids = {
        document_id
        for document_id, (document, _, _) in documents.items()
        if document.processing_status == "failed"
    }
    failed_with_mentions = sorted(
        str(mention.document_id)
        for mention in mentions
        if mention.document_id in failed_document_ids
    )

    repository = MilvusRepository()
    collection = repository.setup_collection()
    collection.load()
    vector_field = next(field for field in collection.schema.fields if field.name == "vector")
    new_ids = {str(mention.id) for mention in new_mentions}
    vector_rows = (
        collection.query(
            expr="id in [" + ", ".join(f'\"{value}\"' for value in new_ids) + "]",
            output_fields=["id", "sku_code", "aspect_label", "sentiment", "week_id", "quality_score"],
            limit=max(1, len(new_ids)),
        )
        if new_ids
        else []
    )
    vector_by_id = {str(row["id"]): row for row in vector_rows}
    metadata_mismatches = []
    for mention in new_mentions:
        row = vector_by_id.get(str(mention.id))
        if row is None:
            continue
        scalar_fields = ("sku_code", "aspect_label", "sentiment", "week_id")
        scalar_mismatch = any(
            row[field] != getattr(mention, field) for field in scalar_fields
        )
        quality_mismatch = abs(
            float(row["quality_score"]) - float(mention.quality_score or 0.0)
        ) > 1e-6
        if scalar_mismatch or quality_mismatch:
            metadata_mismatches.append(str(mention.id))

    return {
        "documents": [
            {
                "document_id": str(document_id),
                "sku_code": sku_code,
                "status": document.processing_status,
                "has_processing_error": document.processing_error is not None,
            }
            for document_id, (document, sku_code, _) in sorted(documents.items(), key=lambda item: str(item[0]))
        ],
        "new_mention_count": len(new_mentions),
        "new_mention_ids": sorted(new_ids),
        "invalid_excerpt_ids": invalid_excerpt_ids,
        "invalid_quality_ids": invalid_quality_ids,
        "invalid_embed_text_ids": invalid_embed_text_ids,
        "failed_documents_with_mentions": failed_with_mentions,
        "milvus_dimension": int(vector_field.params["dim"]),
        "milvus_new_vector_count": len(vector_by_id),
        "missing_new_vectors": sorted(new_ids - vector_by_id.keys()),
        "new_orphan_vectors": sorted(vector_by_id.keys() - new_ids),
        "metadata_mismatches": metadata_mismatches,
    }


async def run(document_id_values: list[str]) -> None:
    if not 1 <= len(document_id_values) <= MAX_ACCEPTANCE_DOCUMENTS:
        raise ValueError(f"Provide between 1 and {MAX_ACCEPTANCE_DOCUMENTS} document IDs")
    document_ids = [UUID(value) for value in document_id_values]
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("document_id values must be unique")

    await init_db()
    try:
        documents = await _load_selected_documents(document_ids)
        repository = MilvusRepository()
        await asyncio.to_thread(repository.setup_collection)
        async with get_db_context() as session:
            baseline_ids = set((await session.execute(select(AspectMention.id))).scalars())

        stats = PipelineRunStats(raw_documents_fetched=len(documents))
        await _run_enrichment_stage(documents, None, stats)
        enriched = await _selected_enriched_documents(document_ids)
        await _run_embedding_stage(
            None,
            repository,
            stats,
            enriched_documents=enriched,
        )
        print(
            json.dumps(
                {
                    "selected": [
                        {"document_id": str(document.id), "sku_code": document.sku_code}
                        for document in documents
                    ],
                    "stats": asdict(stats),
                    "audit": await _audit(document_ids, baseline_ids),
                },
                ensure_ascii=False,
                default=str,
            )
        )
    finally:
        await close_db()


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(run(arguments.document_id))
