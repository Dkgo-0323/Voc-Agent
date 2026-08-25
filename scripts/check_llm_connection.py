"""Run a synthetic, read-only enrichment request against the configured LLM."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from backend.app.core.settings import settings
from backend.app.db.repositories.schemas import DocumentRead
from backend.worker.jobs import build_aspect_extractor
from pipelines.enrichment.aspect_extractor import ExtractionResponseError


async def main() -> None:
    print(f"Checking configured model: {settings.llm_model}", flush=True)
    document = DocumentRead(
        id=uuid4(),
        sku_id=uuid4(),
        sku_code="ecoflow-delta2",
        sku_name="EcoFlow DELTA 2",
        platform="amazon",
        external_id="llm-connection-check",
        title="Synthetic connection check",
        body=(
            "I tested the power station overnight. The fan is extremely loud "
            "while charging, but the battery lasted for eight hours."
        ),
        rating=3,
        author_hash=None,
        source_url=None,
        published_at=None,
        week_id=202634,
        ingested_at=datetime.now(UTC),
        processing_status="raw",
        processing_error=None,
        processed_at=None,
    )
    try:
        result = await build_aspect_extractor(
            timeout_seconds=30, max_retries=0
        ).extract([document])
    except ExtractionResponseError as error:
        if error.raw_response:
            print(f"Rejected model response: {error.raw_response}", flush=True)
        raise
    print(
        json.dumps(
            {
                "model": settings.llm_model,
                "document_count": len(result.documents),
                "aspects": [
                    aspect.model_dump()
                    for extracted in result.documents
                    for aspect in extracted.aspects
                ],
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
