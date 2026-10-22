"""Read-only audit of the exact Phase 14 conversation in a browser receipt.

Requires an explicit receipt and run ID; never searches historical prompts.
This audits the synthetic regression fixture, not a public-review dataset.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).absolute().parents[1]))

from shared.acceptance.receipts import TurnExpectation, audit_turns, validate_receipt

PROMPTS = (
    "Use tool_sql to count reviews and mentions for jackery-explorer-1000 in ISO week 202403.",
    "What noise complaints do customers report about ecoflow-delta2 in ISO week 202403? Include an exact customer example.",
    "Use tool_sql for the review count and tool_rag for an exact customer example about fan noise for ecoflow-delta2 in ISO week 202403.",
    "What about jackery-explorer-1000 for the same week? Use tool_sql for its review count and tool_rag for one exact customer example.",
    "Use tool_rag to check what evidence exists for ecoflow-delta2 in ISO week 202452.",
)

EXPECTATIONS = tuple(
    TurnExpectation(
        prompt,
        frozenset(tools),
        week_id=202403 if index == 3 else None,
        status="abstained" if index == 4 else "success",
        require_citation=index in {1, 2, 3},
    )
    for index, (prompt, tools) in enumerate(
        zip(
            PROMPTS,
            (
                {"tool_sql"},
                {"tool_rag"},
                {"tool_sql", "tool_rag"},
                {"tool_sql", "tool_rag"},
                {"tool_rag"},
            ),
            strict=True,
        )
    )
)


async def verify_agent_traces(receipt: dict, *, run_id: str) -> dict:
    turns = validate_receipt(receipt, run_id=run_id)
    # Delay importing application settings/drivers until CLI inputs are valid.
    from uuid import UUID

    from sqlalchemy import select

    from backend.app.core.database import close_db, get_db_context, init_db
    from backend.app.db.models import ChatMessage
    from scripts.seed_phase14_demo_data import DEMO_MENTIONS, _id

    await init_db()
    try:
        async with get_db_context() as session:
            messages = list(
                (
                    await session.scalars(
                        select(ChatMessage)
                        .where(ChatMessage.session_id == UUID(turns[0]["session_id"]))
                        .order_by(ChatMessage.created_at, ChatMessage.id)
                    )
                ).all()
            )
            return audit_turns(
                receipt,
                messages,
                EXPECTATIONS,
                run_id=run_id,
                allowed_mention_ids={
                    str(_id("mention", i)) for i in range(len(DEMO_MENTIONS))
                },
            )
    finally:
        await close_db()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    print(
        json.dumps(
            asyncio.run(verify_agent_traces(receipt, run_id=args.run_id)), indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
