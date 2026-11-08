"""Business assertions for real-model API replays; no scripted model answers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    tools: tuple[str, ...] = ()
    sku: str | None = None
    citation: bool = False
    count: bool = False
    guidance: bool = False
    operations: tuple[str, ...] = ()
    rubric: str = ""
    require_query: bool = True
    allow_week_filter: bool = False


@dataclass(frozen=True)
class Scenario:
    id: str
    turns: tuple[Question, ...]


def parse_sse(body: str) -> list[dict[str, Any]]:
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        data = [
            line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")
        ]
        if data:
            payload = json.loads("\n".join(data))
            if not isinstance(payload, dict) or "event_type" not in payload:
                raise ValueError("Invalid SSE event")
            events.append(payload)
    return events


def assess(
    question: Question,
    events: list[dict[str, Any]],
    *,
    persisted: dict[str, Any] | None = None,
    expected_count: int | None = None,
) -> list[str]:
    """Fail closed on missing receipts, wrong scope, missing tools and blank answers.

    Keyword/numeric checks are smoke checks, not proof of semantic correctness.
    The question rubric is retained separately for human/independent review.
    """
    failures = []
    terminal = [e for e in events if e["event_type"] in {"error", "done"}]
    if len(terminal) != 1 or not events or events[-1] is not terminal[-1]:
        failures.append("invalid_terminal_sequence")
    errors = [e for e in events if e["event_type"] == "error"]
    failures.extend(
        "api_error:" + e.get("error", {}).get("code", "unknown") for e in errors
    )
    done = next((e for e in terminal if e["event_type"] == "done"), {})
    if done.get("status") not in {"success", "partial", "abstained"}:
        failures.append("unsuccessful_status")
    answer = "".join(
        e.get("delta", "") for e in events if e["event_type"] == "answer_delta"
    )
    if not answer.strip():
        failures.append("empty_answer")
    if "No successful tool result" in answer:
        failures.append("internal_error_exposed")
    if re.search(r"[\u4e00-\u9fff]", question.prompt) and not re.search(
        r"[\u4e00-\u9fff]", answer
    ):
        failures.append("answer_language_mismatch")
    if persisted is None:
        failures.append("missing_persisted_receipt")
        return failures
    if persisted.get("content") != answer or persisted.get("id") != done.get(
        "assistant_message_id"
    ):
        failures.append("persisted_answer_mismatch")
    if (
        persisted.get("session_id") != done.get("session_id")
        or persisted.get("prompt") != question.prompt
    ):
        failures.append("persisted_turn_mismatch")
    results = persisted.get("tool_results") or {}
    if results.get("agent_status") != done.get("status"):
        failures.append("persisted_status_mismatch")
    calls = (persisted.get("tool_calls") or {}).get("calls", [])
    outcomes = {r["call_id"]: r for r in results.get("results", [])}
    supported = [
        c
        for c in calls
        if c.get("executed")
        and outcomes.get(c["call_id"], {}).get("status") in {"success", "partial"}
    ]
    if (
        question.require_query
        and not question.guidance
        and not any(c.get("executed") for c in calls)
    ):
        failures.append("missing_data_query")
    if question.guidance and calls:
        failures.append("unnecessary_data_query")
    for tool in question.tools:
        if not any(c["tool_name"] == tool for c in supported):
            failures.append("missing_successful_tool:" + tool)
    if question.sku:
        scoped = [c for c in calls if c.get("executed")]
        if not scoped or any(
            set((c.get("normalized_arguments") or {}).get("sku_codes", []))
            != {question.sku}
            for c in scoped
        ):
            failures.append("wrong_sku_scope")
    if not question.allow_week_filter and any(
        (c.get("normalized_arguments") or {}).get("week_range") is not None
        for c in calls
        if c.get("executed")
    ):
        failures.append("unrequested_week_filter")
    for operation in question.operations:
        if not any(
            (c.get("normalized_arguments") or {}).get("operation") == operation
            for c in supported
        ):
            failures.append("missing_operation:" + operation)
    citations = [e["citation"] for e in events if e["event_type"] == "citation"]
    ids = [c["mention_id"] for c in citations]
    stored_ids = (persisted.get("cited_ids") or {}).get("mention_ids", [])
    if sorted(ids) != sorted(stored_ids) or len(set(ids)) != len(ids):
        failures.append("citation_receipt_mismatch")
    if question.citation and not citations:
        failures.append("missing_citation")
    if question.sku and any(c.get("sku_code") != question.sku for c in citations):
        failures.append("wrong_citation_sku")
    if question.count:
        # Appended sample sizes cannot rescue an omitted/wrong review count.
        main_answer = answer.split("Data notes:", 1)[0].replace(",", "")
        counts = re.findall(
            r"(\d+)\s*(?:条|个)?\s*(?:评论|评价|reviews?\b)", main_answer, re.I
        ) + re.findall(
            r"(?:评论|评价)(?:总数|数量|数)?\s*(?:为|是|有|共有|总共|：|:)?\s*(\d+)",
            main_answer,
        )
        if expected_count is None:
            failures.append("missing_count_oracle")
        elif str(expected_count) not in counts:
            failures.append("count_oracle_mismatch")
        for call in supported:
            if (call.get("normalized_arguments") or {}).get(
                "operation"
            ) == "review_count":
                args = call["normalized_arguments"]
                if any(
                    args.get(k) is not None
                    for k in ("week_range", "aspect_label", "sentiment")
                ):
                    failures.append("unexpected_count_filter")
    return failures


REPAIR_HINTS = {
    "missing_successful_tool": "检查工具选择提示、模型原始返回和工具错误；不能移除依据校验。",
    "wrong_sku_scope": "检查产品别名、目录与多轮指代；不要把全库数据当成指定产品数据。",
    "count_oracle_mismatch": "检查评论去重、质量阈值、时间范围以及评论数与提及数是否混淆。",
    "missing_citation": "检查向量检索命中、证据回查和最终引用协议。",
    "api_error": "检查模型响应、参数校验和基础设施；先定位错误再修改提示。",
}


def repair_hint(failure: str) -> str:
    return REPAIR_HINTS.get(
        failure.split(":", 1)[0],
        "查看问题、回答、SSE 与持久化记录，修复后重跑同一用例及完整问题集。",
    )
