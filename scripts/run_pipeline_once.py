"""Run the weekly pipeline once with an explicit document limit."""

import argparse
import asyncio
import json
from dataclasses import asdict

from backend.app.core.database import close_db, init_db
from backend.worker.jobs import weekly_pipeline_job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="maximum number of raw documents to enrich (default: 1)",
    )
    return parser.parse_args()


async def run(limit: int) -> None:
    await init_db()
    try:
        stats = await weekly_pipeline_job(document_limit=limit)
        print(json.dumps(asdict(stats), ensure_ascii=False, default=str))
    finally:
        await close_db()


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(run(arguments.limit))
