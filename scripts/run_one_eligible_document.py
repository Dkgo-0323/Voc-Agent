"""Scan raw documents and process exactly one that passes pre-filtering."""

import argparse
import asyncio
import json
from dataclasses import asdict

from backend.app.core.database import close_db, init_db
from backend.worker.jobs import (
    PipelineRunStats,
    _fetch_documents,
    _run_embedding_stage,
    _run_enrichment_stage,
)
from pipelines.embedding.milvus_repo import MilvusRepository
from pipelines.enrichment.aspect_extractor import prepare_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-limit", type=int, default=500)
    return parser.parse_args()


async def run(scan_limit: int) -> None:
    if scan_limit < 1:
        raise ValueError("scan_limit must be positive")
    await init_db()
    try:
        milvus_repository = MilvusRepository()
        await asyncio.to_thread(milvus_repository.setup_collection)
        candidates = await _fetch_documents("raw", scan_limit)
        selected = next(
            (document for document in candidates if prepare_document(document)), None
        )
        if selected is None:
            print(json.dumps({"scanned": len(candidates), "selected": None}))
            return

        stats = PipelineRunStats(raw_documents_fetched=1)
        await _run_enrichment_stage([selected], None, stats)
        if stats.documents_enriched == 1:
            await _run_embedding_stage(
                None,
                milvus_repository,
                stats,
                enriched_documents=[selected],
            )
        print(
            json.dumps(
                {
                    "scanned": len(candidates),
                    "selected_document_id": str(selected.id),
                    "stats": asdict(stats),
                },
                ensure_ascii=False,
                default=str,
            )
        )
    finally:
        await close_db()


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(run(arguments.scan_limit))
