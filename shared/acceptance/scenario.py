"""Explicit dataset expectations, shared with the browser; no service imports."""

import json
from datetime import date
from pathlib import Path

from shared.acceptance.receipts import TurnExpectation


def load_scenario(path: Path | None = None) -> dict:
    value = json.loads((path or Path(__file__).with_name("synthetic-scenario.json"))
                       .read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Invalid scenario schema")
    for key in ("report_sku", "citation_text"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"Invalid scenario {key}")
    weeks = [value.get("report_week")]
    turns = value.get("turns")
    if not isinstance(turns, list) or len(turns) != 5:
        raise ValueError("Scenario requires five turns")
    for turn in turns:
        if not isinstance(turn, dict):
            raise ValueError("Invalid scenario turn")
        if not isinstance(turn.get("prompt"), str) or not turn["prompt"].strip():
            raise ValueError("Invalid scenario prompt")
        tools = turn.get("tools")
        if (not isinstance(tools, list) or not tools
                or any(not isinstance(t, str) or t not in {"tool_sql", "tool_rag", "tool_report"} for t in tools)
                or len(set(tools)) != len(tools)):
            raise ValueError("Invalid scenario tools")
        if (turn.get("status") not in {"success", "partial", "abstained"}
                or type(turn.get("require_citation")) is not bool
                or (turn["status"] == "abstained" and turn["require_citation"])):
            raise ValueError("Invalid scenario outcome")
        weeks.append(turn.get("week_id"))
    for week in weeks:
        if type(week) is not int:
            raise ValueError("Invalid scenario ISO week")
        date.fromisocalendar(week // 100, week % 100, 1)
    return value


def turn_expectations(scenario: dict) -> tuple[TurnExpectation, ...]:
    return tuple(TurnExpectation(
        prompt=t["prompt"], tools=frozenset(t["tools"]), week_id=t["week_id"],
        status=t["status"], require_citation=t["require_citation"],
    ) for t in scenario["turns"])
