"""Validate exact persisted turns. No settings, database or model imports.

This audits identity, tools and citation scope, not semantics/retrieval quality.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class TurnExpectation:
    prompt: str
    tools: frozenset[str]
    status: str | None = None
    week_id: int | None = None
    require_citation: bool = False


def uuid_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Receipt identifiers must be UUID strings")
    return str(UUID(value))


def validate_receipt(
    receipt: Mapping[str, Any], *, run_id: str
) -> list[dict[str, str]]:
    if not isinstance(receipt, Mapping):
        raise ValueError("Receipt must be a JSON object")
    if receipt.get("schema_version") != 1:
        raise ValueError("Unsupported receipt schema")
    if uuid_text(receipt.get("run_id")) != uuid_text(run_id):
        raise ValueError("Receipt belongs to a different run")
    turns = receipt.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("Receipt must contain turns")
    normalized = []
    message_ids: set[str] = set()
    session_ids: set[str] = set()
    for turn in turns:
        if not isinstance(turn, dict):
            raise ValueError("Invalid receipt turn")
        row = {
            key: uuid_text(turn.get(key))
            for key in ("session_id", "user_message_id", "assistant_message_id")
        }
        for key in ("user_message_id", "assistant_message_id"):
            if row[key] in message_ids:
                raise ValueError("Receipt repeats a message ID")
            message_ids.add(row[key])
        session_ids.add(row["session_id"])
        normalized.append(row)
    if len(session_ids) != 1:
        raise ValueError("Follow-up turns must share one session")
    return normalized


def audit_turns(
    receipt: Mapping[str, Any],
    messages: Sequence[Any],
    expectations: Sequence[TurnExpectation],
    *,
    run_id: str,
    allowed_mention_ids: set[str],
) -> dict[str, Any]:
    """Audit all session rows, ordered by creation time; reject extra/missing rows."""
    turns = validate_receipt(receipt, run_id=run_id)
    if len(turns) != len(expectations) or len(messages) != 2 * len(turns):
        raise ValueError("Persisted conversation/receipt has an unexpected turn count")
    allowed = {uuid_text(value) for value in allowed_mention_ids}
    cited: set[str] = set()
    for index, (turn, expectation) in enumerate(zip(turns, expectations, strict=True)):
        user, assistant = messages[index * 2 : index * 2 + 2]
        for row, role, key in (
            (user, "user", "user_message_id"),
            (assistant, "assistant", "assistant_message_id"),
        ):
            if (
                str(row.id) != turn[key]
                or str(row.session_id) != turn["session_id"]
                or row.role != role
            ):
                raise ValueError(
                    f"Turn {index + 1}: persisted message identity mismatch"
                )
        if user.content != expectation.prompt:
            raise ValueError(f"Turn {index + 1}: persisted prompt mismatch")
        status = (assistant.tool_results or {}).get("agent_status")
        if status not in {"success", "partial", "abstained"}:
            raise ValueError(
                f"Turn {index + 1}: answer has no successful persisted status"
            )
        if expectation.status is not None and status != expectation.status:
            raise ValueError(f"Turn {index + 1}: unexpected Agent status")
        calls = [
            call
            for call in (assistant.tool_calls or {}).get("calls", [])
            if call.get("executed") is True
        ]
        if not expectation.tools <= {call.get("tool_name") for call in calls}:
            raise ValueError(f"Turn {index + 1}: required tools were not executed")
        if expectation.week_id is not None and not any(
            (call.get("normalized_arguments") or {}).get("week_range")
            == {
                "start_week_id": expectation.week_id,
                "end_week_id": expectation.week_id,
            }
            for call in calls
        ):
            raise ValueError(
                f"Turn {index + 1}: expected week missing from executed tools"
            )
        ids = (assistant.cited_ids or {}).get("mention_ids", [])
        if not isinstance(ids, list):
            raise ValueError(f"Turn {index + 1}: invalid citation metadata")
        turn_cited = {uuid_text(value) for value in ids}
        if len(turn_cited) != len(ids) or not turn_cited <= allowed:
            raise ValueError(f"Turn {index + 1}: duplicate or out-of-scope citation")
        if expectation.require_citation and not turn_cited:
            raise ValueError(f"Turn {index + 1}: expected traceable citation")
        if status == "abstained" and turn_cited:
            raise ValueError(
                f"Turn {index + 1}: abstention unexpectedly cites evidence"
            )
        cited.update(turn_cited)
    return {
        "schema_version": 1,
        "run_id": uuid_text(run_id),
        "session_id": turns[0]["session_id"],
        "verified_turns": len(turns),
        "traceable_citation_ids": sorted(cited),
        "scope": "persisted identity, tools, status and allowed citation IDs only",
    }
