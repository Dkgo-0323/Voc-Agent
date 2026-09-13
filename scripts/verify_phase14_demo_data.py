"""Audit the isolated Phase 14 fixture across PostgreSQL and Milvus."""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select

from backend.app.core.database import close_db, get_db_context, init_db
from backend.app.core.settings import settings
from backend.app.db.models import AspectMention, Document
from pipelines.embedding.milvus_repo import MilvusRepository
from scripts.seed_phase14_demo_data import DEMO_MENTIONS, _id


async def verify_demo_data() -> None:
    expected_ids = {_id("mention", index) for index in range(len(DEMO_MENTIONS))}
    await init_db()
    try:
        async with get_db_context() as session:
            rows = (
                await session.execute(
                    select(
                        AspectMention.id,
                        AspectMention.quality_score,
                        AspectMention.embed_text,
                        Document.processing_status,
                    )
                    .join(Document, Document.id == AspectMention.document_id)
                    .where(Document.platform == "phase14-demo")
                )
            ).all()
    finally:
        await close_db()

    postgres_ids = {row.id for row in rows}
    qualified = sum(
        row.quality_score >= settings.aspect_quality_threshold for row in rows
    )
    embedded = sum(row.processing_status == "embedded" for row in rows)
    embed_texts = sum(bool(row.embed_text) for row in rows)

    collection = MilvusRepository().setup_collection()
    collection.load()
    vector_rows = collection.query(
        expr="",
        output_fields=["id", "quality_score"],
        limit=100,
    )
    vector_ids = {UUID(str(row["id"])) for row in vector_rows}

    if postgres_ids != expected_ids:
        raise RuntimeError("PostgreSQL Phase 14 mention IDs do not match the fixture")
    if vector_ids != expected_ids:
        raise RuntimeError("Milvus IDs do not exactly match PostgreSQL aspect_mentions.id")
    if embedded != len(DEMO_MENTIONS) or embed_texts != len(DEMO_MENTIONS):
        raise RuntimeError("One or more Phase 14 records are not fully embedded")
    if qualified != 9:
        raise RuntimeError("The quality-threshold fixture must expose exactly 9 mentions")

    print(f"postgres_mentions={len(postgres_ids)}")
    print(f"milvus_vectors={len(vector_ids)}")
    print(f"uuid_provenance_matches={postgres_ids == vector_ids}")
    print(f"embedded_documents={embedded}")
    print(f"quality_qualified_mentions={qualified}")
    print(f"quality_filtered_mentions={len(rows) - qualified}")


if __name__ == "__main__":
    asyncio.run(verify_demo_data())
