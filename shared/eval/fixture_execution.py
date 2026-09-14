"""Controlled Agent-result fixtures for repeatable semantic evaluation.

These observations mirror the explicit Week 3 router fixture assumptions used
by the Phase 11 dataset. They are not a substitute for live-provider release
validation; they make all 50 evaluation cases executable in CI today.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid5

from backend.app.agent.schemas import (
    AgentExecutionMetadata,
    AgentRunResult,
    AgentStatus,
    AnswerCitation,
    ExpandedSourceMetadata,
    ToolCallTrace,
    ToolError,
    ToolStatus,
)
from shared.eval.rag_eval import ObservedCase
from shared.eval.semantic_golden import (
    CitationExpectation,
    SemanticGoldenCase,
    SemanticGoldenDataset,
    Tool,
)

_FIXTURE_NAMESPACE = UUID("4e3f3c7a-6f28-45bf-b4bb-1052b44d5085")
_FIXTURE_TIME = datetime(2024, 1, 19, tzinfo=UTC)


def _tool_trace(case: SemanticGoldenCase, tool: Tool) -> ToolCallTrace:
    arguments: dict[str, object]
    if tool is Tool.REPORT:
        arguments = {
            "sku_code": case.scope.sku_codes[0] if case.scope.sku_codes else "unknown",
            "week_id": case.scope.week_ids[-1] if case.scope.week_ids else 202403,
        }
    else:
        arguments = {"sku_codes": list(case.scope.sku_codes)}
        if case.scope.week_ids:
            arguments["week_range"] = {
                "start_week_id": min(case.scope.week_ids),
                "end_week_id": max(case.scope.week_ids),
            }
    error: ToolError | None = None
    status = ToolStatus.SUCCESS
    if case.case_id in {"SG17", "SG46"}:
        status = ToolStatus.ERROR
        error = ToolError(
            code="capacity_tier_mismatch",
            message="Direct SKU comparison requires the same capacity tier.",
        )
    elif case.case_id in {"SG44"}:
        status = ToolStatus.ERROR
        error = ToolError(
            code="unknown_or_disabled_sku",
            message="One or more SKU codes are unknown or not dashboard-enabled.",
        )
    elif case.case_id in {"SG45", "SG49"}:
        status = ToolStatus.ERROR
        error = ToolError(code="invalid_week_id", message="week_id must be a valid ISO week identifier.")
    elif case.case_id in {"SG42", "SG43"}:
        status = ToolStatus.EMPTY
    elif case.case_id == "SG48" and tool is Tool.REPORT:
        status = ToolStatus.NOT_FOUND
    return ToolCallTrace(
        call_id=f"{case.case_id}-{tool.value}",
        tool_name=tool.value,
        normalized_arguments=arguments,
        executed=True,
        status=status,
        duration_ms=1,
        result_count=0 if status in {ToolStatus.EMPTY, ToolStatus.NOT_FOUND, ToolStatus.ERROR} else 1,
        error=error,
    )


def _citation(case: SemanticGoldenCase) -> AnswerCitation:
    mention_id = uuid5(_FIXTURE_NAMESPACE, f"{case.case_id}:mention")
    document_id = uuid5(_FIXTURE_NAMESPACE, f"{case.case_id}:document")
    sku_code = case.scope.sku_codes[0]
    positive = case.case_id == "SG27"
    return AnswerCitation(
        mention_id=mention_id,
        document_id=document_id,
        evidence_preview=(
            "the unit is quiet and reliable" if positive else "the fan is very loud under load"
        ),
        sku_code=sku_code,
        aspect_label="noise_level",
        sentiment="positive" if positive else "negative",
        week_id=case.scope.week_ids[-1] if case.scope.week_ids else 202403,
        source=ExpandedSourceMetadata(
            document_id=document_id,
            sku_code=sku_code,
            platform="fixture",
            published_at=_FIXTURE_TIME,
            source_url="https://example.invalid/voc-fixture",
            review_text=(
                "The unit is quiet and reliable." if positive else "The fan is very loud under load."
            ),
        ),
    )


def _answer(case: SemanticGoldenCase) -> str:
    if case.case_id in {"SG17", "SG46"}:
        return "Direct SKU comparison requires the same capacity tier, so no winner is provided."
    if case.case_id in {"SG42", "SG43"}:
        return "No matching quality-qualified VOC data is available for this request."
    if case.case_id in {"SG44", "SG45", "SG49"}:
        return "The request could not be validated safely; no product claim is provided."
    if case.case_id == "SG50":
        return "Stored reports have no durable report-to-mention citation mapping."
    specific = {
        "SG01": "The fixture contains 12 negative mentions across 8 reviews.",
        "SG02": "Noise has 7 negative mentions and charging has 5 in the fixture.",
        "SG03": "The fixture's deterministic sentiment distribution includes 12 negative mentions.",
        "SG04": "The fixture contains 5 negative charging mentions for Delta 2.",
        "SG05": "Noise is the leading negative Delta 2 aspect with 7 mentions.",
        "SG06": "The fixture contains 12 Delta 2 VOC mentions in week 202403.",
        "SG07": "Delta 2 has a 50% negative rate in the same-tier fixture comparison.",
        "SG08": "Delta 2 negative sentiment worsened from 25% in 202402 to 50% in 202403.",
        "SG09": "The deterministic noise trend rises from 25% negative to 50% negative across the fixture weeks.",
        "SG10": "Delta 2 negativity worsened because the calculated rate increased from 25% to 50%.",
        "SG11": "Delta 2's weekly negative rate is 25% in 202402 and 50% in 202403.",
        "SG12": "The fixture's charging trend must be reported from deterministic aspect-trend output; it does not support a causal explanation.",
        "SG13": "Yes. The latest fixture week is higher at 50% negative versus 25% in the prior week.",
        "SG14": "For the same-tier comparison, Delta 2 is 50% negative and Jackery Explorer 1000 is 25% negative.",
        "SG15": "Delta 2 has a 50% negative rate versus 25% for Jackery Explorer 1000; this is a neutral same-tier comparison.",
        "SG16": "For same-tier SKUs, Delta 2 noise negativity is 50% versus 25% for Jackery Explorer 1000; neither is declared a winner.",
        "SG19": "The same-tier comparison reports the two SKUs' deterministic negative mention counts and retains the low-sample caveat.",
        "SG20": "Jackery Explorer 1000 has the lower fixture negative rate, 25% versus 50% for Delta 2, but the sample caveat prevents a broad superiority claim.",
        "SG31": "Noise is the leading Delta 2 complaint with 7 mentions in fixture week 202403.",
        "SG32": "Delta 2 negativity rose from 25% to 50%; the retrieved fan-noise complaint illustrates a possible feedback theme but does not prove a causal reason.",
        "SG33": "Noise is the most common Delta 2 complaint category with 7 mentions.",
        "SG35": "Delta 2 has 12 negative mentions in the fixture.",
        "SG36": "Fixture-week Delta 2 negative feedback contains 12 negative mentions, with noise leading at 7 mentions.",
        "SG37": "For the visible Delta 2 and Jackery 1000 comparison, noise negativity is 50% versus 25%.",
        "SG39": "For the visible Delta 2 context, the fixture contains 12 negative mentions.",
        "SG41": "Using the visible same-tier pair, the deterministic trend comparison should preserve the two requested SKUs and their weekly values.",
        "SG47": "Stored report for Delta 2, week 202403: the persisted report content is returned verbatim without regeneration.",
        "SG48": "No stored report exists; deterministic analytics found 12 negative mentions, so no report was generated.",
    }
    if case.case_id in specific:
        return specific[case.case_id]
    values = []
    for expected in case.numeric_expectations:
        value = expected.value
        values.append(f"{value * 100:g}%" if isinstance(value, float) and value < 1 else str(value))
    metrics = ", ".join(values) if values else "the supported VOC result"
    evidence = (
        f" A retrieved review says {_citation(case).evidence_preview}."
        if case.citation_expectation is CitationExpectation.REQUIRED
        else ""
    )
    return f"The fixture supports {metrics}.{evidence}"


def fixture_result(case: SemanticGoldenCase) -> AgentRunResult:
    traces = [_tool_trace(case, tool) for tool in case.required_tools]
    status = AgentStatus.ABSTAINED if case.case_id in {"SG42", "SG43"} else AgentStatus.SUCCESS
    citations = [_citation(case)] if case.citation_expectation is CitationExpectation.REQUIRED else []
    return AgentRunResult(
        status=status,
        final_answer=_answer(case),
        citations=citations,
        tool_trace=traces,
        execution=AgentExecutionMetadata(
            model_round_count=1,
            attempted_tool_call_count=len(traces),
            executed_tool_call_count=len(traces),
            maximum_tool_calls=3,
        ),
    )


async def fixture_executor(case: SemanticGoldenCase) -> AgentRunResult:
    return fixture_result(case)


def fixture_observations(dataset: SemanticGoldenDataset) -> list[ObservedCase]:
    return [ObservedCase(case_id=case.case_id, result=fixture_result(case)) for case in dataset.cases]
