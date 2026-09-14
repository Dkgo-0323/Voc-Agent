"""Seed deterministic, traceable demo data for the isolated Phase 14 environment.

Run this only after Alembic and ``backend.app.db.seed`` against a disposable
database. The script upserts a small fixture and writes the matching vectors to
the configured Milvus collection, so it never requires production review data.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, update

from backend.app.core.database import close_db, get_db_context, init_db
from backend.app.db.models import AspectMention, Document, Sku
from pipelines.embedding.embedder import Embedder, EmbeddingInput, build_embed_text
from pipelines.embedding.milvus_repo import MilvusRecord, MilvusRepository

DEMO_NAMESPACE = uuid5(NAMESPACE_URL, "voc-agent-phase14-demo")


@dataclass(frozen=True)
class DemoMention:
    sku_code: str
    sku_name: str
    week_id: int
    body: str
    mention_text: str
    aspect_label: str
    sentiment: str
    quality_score: float = 0.9


DEMO_MENTIONS = (
    DemoMention(
        "ecoflow-delta2",
        "EcoFlow DELTA 2",
        202402,
        "The Delta 2 battery lasted through a weekend campsite without a recharge.",
        "battery lasted through a weekend campsite",
        "battery_capacity",
        "positive",
    ),
    DemoMention(
        "jackery-explorer-1000",
        "Jackery Explorer 1000",
        202402,
        "Explorer 1000 charged my laptop and lanterns quietly during the camping trip.",
        "charged my laptop and lanterns quietly",
        "noise_level",
        "positive",
    ),
    DemoMention(
        "ecoflow-delta2",
        "EcoFlow DELTA 2",
        202403,
        "The fan is extremely loud while charging in a quiet tent, although runtime is excellent.",
        "fan is extremely loud",
        "noise_level",
        "negative",
    ),
    DemoMention(
        "ecoflow-delta2",
        "EcoFlow DELTA 2",
        202403,
        "Battery lasted all night powering a CPAP and phones during the outage.",
        "Battery lasted all night",
        "battery_capacity",
        "positive",
    ),
    DemoMention(
        "jackery-explorer-1000",
        "Jackery Explorer 1000",
        202403,
        "The Explorer 1000 recharged quickly from AC and the fan stayed quiet.",
        "recharged quickly from AC",
        "charging_speed",
        "positive",
    ),
    DemoMention(
        "jackery-explorer-1000",
        "Jackery Explorer 1000",
        202403,
        "The display is hard to read in bright sunlight but power output was reliable.",
        "display is hard to read in bright sunlight",
        "display_interface",
        "negative",
    ),
    DemoMention(
        "jackery-explorer-300",
        "Jackery Explorer 300",
        202403,
        "The Explorer 300 is light enough to carry from the car to the campsite.",
        "light enough to carry",
        "weight_portability",
        "positive",
    ),
    DemoMention(
        "jackery-explorer-240",
        "Jackery Explorer 240",
        202403,
        "The Explorer 240 ran out of battery before our camping morning was over.",
        "ran out of battery",
        "battery_capacity",
        "negative",
    ),
    DemoMention(
        "anker-solix-f2000",
        "Anker SOLIX F2000",
        202403,
        "The SOLIX F2000 case feels solid and the wheels made moving it easier.",
        "case feels solid",
        "build_quality",
        "positive",
    ),
    DemoMention(
        "ecoflow-delta2",
        "EcoFlow DELTA 2",
        202403,
        "Great product.",
        "Great product",
        "build_quality",
        "positive",
        0.2,
    ),
)


def _id(kind: str, index: int) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"{kind}:{index}")


async def seed_demo_data() -> None:
    await init_db()
    try:
        async with get_db_context() as session:
            sku_ids = dict((await session.execute(select(Sku.sku_code, Sku.id))).all())
            missing = sorted({item.sku_code for item in DEMO_MENTIONS} - sku_ids.keys())
            if missing:
                raise RuntimeError(
                    f"Run backend.app.db.seed first; missing SKUs: {missing}"
                )
            for index, item in enumerate(DEMO_MENTIONS):
                document_id = _id("document", index)
                mention_id = _id("mention", index)
                await session.merge(
                    Document(
                        id=document_id,
                        sku_id=sku_ids[item.sku_code],
                        platform="phase14-demo",
                        external_id=f"phase14-{index}",
                        title=f"Phase 14 demo review {index + 1}",
                        body=item.body,
                        rating=4 if item.sentiment == "positive" else 2,
                        author_hash=f"phase14-{index}",
                        source_url=f"https://example.invalid/phase14/{index}",
                        published_at=datetime.fromisocalendar(
                            item.week_id // 100, item.week_id % 100, 1
                        ),
                        week_id=item.week_id,
                        processing_status="embedded",
                        processed_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
                await session.merge(
                    AspectMention(
                        id=mention_id,
                        document_id=document_id,
                        sku_code=item.sku_code,
                        aspect_label=item.aspect_label,
                        sentiment=item.sentiment,
                        sentiment_score=1.0 if item.sentiment == "positive" else -1.0,
                        confidence=0.95,
                        mention_text=item.mention_text,
                        context_window=item.body[:200],
                        quality_score=item.quality_score,
                        week_id=item.week_id,
                    )
                )

        inputs = [
            EmbeddingInput(
                item.sku_name, item.aspect_label, item.mention_text, item.body
            )
            for item in DEMO_MENTIONS
        ]
        texts = [build_embed_text(item) for item in inputs]
        vectors = await Embedder().embed(texts)
        async with get_db_context() as session:
            for index, text in enumerate(texts):
                await session.execute(
                    update(AspectMention)
                    .where(AspectMention.id == _id("mention", index))
                    .values(embed_text=text)
                )
        records = [
            MilvusRecord(
                id=_id("mention", index),
                vector=vector,
                sku_code=item.sku_code,
                aspect_label=item.aspect_label,
                sentiment=item.sentiment,
                week_id=item.week_id,
                quality_score=item.quality_score,
            )
            for index, (item, vector) in enumerate(
                zip(DEMO_MENTIONS, vectors, strict=True)
            )
        ]
        inserted = MilvusRepository().upsert_vectors(records)
        print(f"phase14_demo_documents={len(DEMO_MENTIONS)}")
        print(f"phase14_demo_vectors_upserted={inserted}")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
