"""Verify persisted Agent boundaries from the Phase 14 browser conversation."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.app.core.database import close_db, get_db_context, init_db
from backend.app.db.models import ChatMessage, ChatSession
from scripts.seed_phase14_demo_data import DEMO_MENTIONS, _id

FIRST_PROMPT = (
    "Use tool_sql to count reviews and mentions for jackery-explorer-1000 "
    "in ISO week 202403."
)


def _tool_names(message: ChatMessage) -> set[str]:
    envelope = message.tool_calls or {}
    return {call["tool_name"] for call in envelope.get("calls", [])}


async def verify_agent_traces() -> None:
    await init_db()
    try:
        async with get_db_context() as session:
            session_ids = (
                await session.scalars(
                    select(ChatSession.id).order_by(ChatSession.updated_at.desc())
                )
            ).all()
            conversation: list[ChatMessage] | None = None
            for session_id in session_ids:
                messages = list(
                    (
                        await session.scalars(
                            select(ChatMessage)
                            .where(ChatMessage.session_id == session_id)
                            .order_by(ChatMessage.created_at, ChatMessage.id)
                        )
                    ).all()
                )
                if any(
                    message.role == "user" and message.content == FIRST_PROMPT
                    for message in messages
                ):
                    conversation = messages
                    break
    finally:
        await close_db()

    if conversation is None:
        raise RuntimeError("No completed Phase 14 Agent conversation was found")

    assistants = [message for message in conversation if message.role == "assistant"]
    if len(assistants) != 5:
        raise RuntimeError("The Phase 14 Agent conversation must contain five answers")
    expected_tools = [
        {"tool_sql"},
        {"tool_rag"},
        {"tool_sql", "tool_rag"},
        {"tool_sql", "tool_rag"},
        {"tool_rag"},
    ]
    actual_tools = [_tool_names(message) for message in assistants]
    if any(not expected <= actual for expected, actual in zip(expected_tools, actual_tools, strict=True)):
        raise RuntimeError(f"Unexpected Phase 14 Agent tool coverage: {actual_tools}")

    follow_up_calls = (assistants[3].tool_calls or {}).get("calls", [])
    if not any(
        call.get("normalized_arguments", {}).get("week_range")
        == {"start_week_id": 202403, "end_week_id": 202403}
        for call in follow_up_calls
    ):
        raise RuntimeError("The follow-up did not recover the visible conversation week")
    if (assistants[4].tool_results or {}).get("agent_status") != "abstained":
        raise RuntimeError("The no-data turn did not persist an abstention")

    expected_ids = {_id("mention", index) for index in range(len(DEMO_MENTIONS))}
    cited_ids = {
        cited_id
        for message in assistants
        for cited_id in (message.cited_ids or {}).get("mention_ids", [])
    }
    if not cited_ids or not cited_ids <= {str(value) for value in expected_ids}:
        raise RuntimeError("Agent citations are not traceable to the Phase 14 fixture")

    print("quantitative_tool_sql=True")
    print("qualitative_tool_rag=True")
    print("hybrid_sql_rag=True")
    print("follow_up_week_from_recent_context=202403")
    print(f"traceable_citation_ids={len(cited_ids)}")
    print("no_data_status=abstained")


if __name__ == "__main__":
    asyncio.run(verify_agent_traces())
