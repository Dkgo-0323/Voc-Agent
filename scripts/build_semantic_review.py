"""Build an evidence review bundle from an API replay, without model calls.

Recompute saved analytics queries against the current database. This is a fresh
read-only oracle, not a claim that the data snapshot is identical to the replay.
"""

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def build(source: Path, output: Path) -> None:
    from backend.app.core.settings import settings

    settings.app_env = "production"
    from backend.app.agent.schemas import AnalyticsToolArguments
    from backend.app.agent.tool_sql import AnalyticsService
    from backend.app.core.database import close_db, get_db_context, init_db
    from backend.app.db.repositories.analytics_repo import AnalyticsRepository

    raw = source.read_bytes()
    report = json.loads(raw)
    bundle = {
        "source": str(source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "Fresh analytics oracle plus saved citation sources; no model calls; semantic verdicts require review",
        "turns": [],
    }
    try:
        await init_db()
        async with get_db_context() as db:
            service = AnalyticsService(AnalyticsRepository(db))
            for row in report["results"]:
                persisted = row.get("persisted") or {}
                oracles = []
                for call in (persisted.get("tool_calls") or {}).get("calls", []):
                    if (
                        call.get("executed")
                        and call.get("tool_name") == "tool_sql"
                        and call.get("normalized_arguments")
                    ):
                        result = await service.execute(
                            AnalyticsToolArguments.model_validate(
                                call["normalized_arguments"]
                            )
                        )
                        oracles.append(
                            {
                                "call_id": call["call_id"],
                                "result": result.model_dump(mode="json"),
                            }
                        )
                bundle["turns"].append(
                    {
                        "scenario": row["scenario"],
                        "question_id": row["question_id"],
                        "prompt": row["prompt"],
                        "rubric": row.get("rubric", ""),
                        "answer": persisted.get("content", ""),
                        "automatic_pass": row["automatic_pass"],
                        "analytics_oracles": oracles,
                        "citations": [
                            e["citation"]
                            for e in row.get("events", [])
                            if e["event_type"] == "citation"
                        ],
                        "semantic_review": "pending",
                    }
                )
    finally:
        await close_db()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Built {len(bundle['turns'])} review turns: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(build(args.report, args.output))
