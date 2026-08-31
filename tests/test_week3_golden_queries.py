"""Deterministic Week 3 smoke/golden query acceptance set.

The suite exercises the real function-calling router and production schemas while
replacing external LLM, PostgreSQL, and Milvus calls with controlled results.  It
is intentionally the small Week 3 seed set, not the Week 4 evaluation system.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from backend.app.agent.llm import ModelResponse, ModelToolCall
from backend.app.agent.router import (
    MAX_TOOL_CALLS,
    NO_DATA_ANSWER,
    VOC_SYSTEM_POLICY,
    FunctionCallingRouter,
    ToolBinding,
)
from backend.app.agent.schemas import (
    AgentSchema,
    AgentStatus,
    AnalyticsOperation,
    AnalyticsToolArguments,
    AnalyticsToolResult,
    AspectBucket,
    AspectDistributionPayload,
    ComparisonMetric,
    ConversationMessage,
    ExpandedSourceMetadata,
    RagRetrievalPayload,
    RagToolArguments,
    RagToolResult,
    ReportToolArguments,
    ReportToolResult,
    RetrievedEvidence,
    ReviewCountPayload,
    Sentiment,
    SkuComparisonMetrics,
    SkuComparisonPayload,
    SkuSampleCount,
    ToolError,
    ToolExecutionMetadata,
    ToolName,
    ToolStatus,
    ToolWarning,
    TrendPayload,
    TrendPoint,
    WeeklyReportPayload,
)


FIXTURE_WEEK = 202403
FIXTURE_RANGE = {"start_week_id": 202402, "end_week_id": 202403}
DELTA_2 = "ecoflow-delta2"
JACKERY_1000 = "jackery-explorer-1000"
ANKER_F2000 = "anker-solix-f2000"
EVIDENCE_QUOTE = "the fan is very loud under load"
SMALL_SAMPLE_MESSAGE = (
    "jackery-explorer-1000 has 8 matching reviews, below the reliability "
    "threshold of 20."
)


@dataclass(frozen=True)
class GoldenCall:
    tool_name: ToolName
    arguments: dict[str, Any]
    outcome: str = "success"


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    category: str
    query: str
    calls: tuple[GoldenCall, ...]
    answer: str
    expected_status: AgentStatus = AgentStatus.SUCCESS
    expected_citations: int = 0
    expected_warning_codes: tuple[str, ...] = ()
    recent_messages: tuple[ConversationMessage, ...] = ()
    notes: str = ""


def sql(arguments: dict[str, Any], *, outcome: str = "success") -> GoldenCall:
    return GoldenCall(ToolName.SQL, arguments, outcome)


def rag(arguments: dict[str, Any], *, outcome: str = "success") -> GoldenCall:
    return GoldenCall(ToolName.RAG, arguments, outcome)


def report(arguments: dict[str, Any], *, outcome: str = "success") -> GoldenCall:
    return GoldenCall(ToolName.REPORT, arguments, outcome)


GOLDEN_CASES = (
    GoldenCase(
        "Q01",
        "count_distribution",
        "How many negative mentions did EcoFlow Delta 2 receive in fixture week 202403?",
        (
            sql(
                {
                    "operation": "review_count",
                    "sku_codes": [DELTA_2],
                    "week_range": {
                        "start_week_id": FIXTURE_WEEK,
                        "end_week_id": FIXTURE_WEEK,
                    },
                    "sentiment": "negative",
                }
            ),
        ),
        "The deterministic fixture contains 12 negative mentions across 8 reviews.",
    ),
    GoldenCase(
        "Q02",
        "count_distribution",
        "What are the main complaint aspects for EcoFlow Delta 2 in fixture week 202403?",
        (
            sql(
                {
                    "operation": "aspect_distribution",
                    "sku_codes": [DELTA_2],
                    "week_range": {
                        "start_week_id": FIXTURE_WEEK,
                        "end_week_id": FIXTURE_WEEK,
                    },
                    "sentiment": "negative",
                }
            ),
        ),
        "Noise has 7 fixture mentions and charging has 5.",
    ),
    GoldenCase(
        "Q03",
        "trend",
        "How has negative sentiment for EcoFlow Delta 2 changed over the fixture weeks?",
        (
            sql(
                {
                    "operation": "trend",
                    "sku_codes": [DELTA_2],
                    "week_range": FIXTURE_RANGE,
                    "sentiment": "negative",
                }
            ),
        ),
        "The deterministic negative rate rises from 25% to 50%.",
    ),
    GoldenCase(
        "Q04",
        "trend",
        "How has fan and noise sentiment changed over the fixture weeks?",
        (
            sql(
                {
                    "operation": "aspect_trend",
                    "sku_codes": [DELTA_2],
                    "week_range": FIXTURE_RANGE,
                    "aspect_label": "noise_level",
                }
            ),
        ),
        "The deterministic noise trend rises from 25% to 50% negative.",
    ),
    GoldenCase(
        "Q05",
        "comparison",
        "Compare EcoFlow Delta 2 and Jackery Explorer 1000 using customer feedback.",
        (
            sql(
                {
                    "operation": "compare_skus",
                    "sku_codes": [DELTA_2, JACKERY_1000],
                    "comparison_metric": "negative_rate",
                },
                outcome="small_sample",
            ),
        ),
        "The fixture negative rates are 50% for Delta 2 and 25% for Jackery 1000.",
        expected_warning_codes=("small_sample",),
    ),
    GoldenCase(
        "Q06",
        "comparison",
        "Compare their noise-related feedback and show one traceable example.",
        (
            sql(
                {
                    "operation": "compare_skus",
                    "sku_codes": [DELTA_2, JACKERY_1000],
                    "aspect_label": "noise_level",
                    "comparison_metric": "negative_rate",
                }
            ),
            rag(
                {
                    "query": "noise feedback",
                    "sku_codes": [DELTA_2, JACKERY_1000],
                    "aspect_label": "noise_level",
                    "top_k": 4,
                }
            ),
        ),
        'The fixture comparison is supported by the comment "{quote}."',
        expected_citations=1,
    ),
    GoldenCase(
        "Q07",
        "comparison",
        "Compare EcoFlow Delta 2 directly with Anker Solix F2000.",
        (
            sql(
                {
                    "operation": "compare_skus",
                    "sku_codes": [DELTA_2, ANKER_F2000],
                    "comparison_metric": "negative_rate",
                },
                outcome="capacity_tier_mismatch",
            ),
        ),
        "A direct comparison is not valid for these capacity tiers.",
        notes="Application-enforced cross-tier constraint.",
    ),
    GoldenCase(
        "Q08",
        "evidence",
        "Show me actual complaints about Delta 2 fan noise.",
        (
            rag(
                {
                    "query": "fan noise complaints",
                    "sku_codes": [DELTA_2],
                    "sentiment": "negative",
                    "aspect_label": "noise_level",
                    "top_k": 5,
                }
            ),
        ),
        'A retrieved complaint says "{quote}."',
        expected_citations=1,
    ),
    GoldenCase(
        "Q09",
        "evidence",
        "Give me examples of negative charging feedback for Delta 2.",
        (
            rag(
                {
                    "query": "negative charging feedback",
                    "sku_codes": [DELTA_2],
                    "sentiment": "negative",
                    "aspect_label": "charging_experience",
                    "top_k": 5,
                }
            ),
        ),
        'The retrieved fixture evidence says "{quote}."',
        expected_citations=1,
    ),
    GoldenCase(
        "Q10",
        "evidence",
        "What exact words do users use about supported noise issues?",
        (
            rag(
                {
                    "query": "exact words about noise",
                    "sku_codes": [DELTA_2],
                    "aspect_label": "noise_level",
                    "top_k": 3,
                }
            ),
        ),
        'The exact retrieved excerpt is "{quote}."',
        expected_citations=1,
    ),
    GoldenCase(
        "Q11",
        "combined",
        "What are the main complaints about Delta 2 in fixture week 202403?",
        (
            sql(
                {
                    "operation": "aspect_distribution",
                    "sku_codes": [DELTA_2],
                    "week_range": {
                        "start_week_id": FIXTURE_WEEK,
                        "end_week_id": FIXTURE_WEEK,
                    },
                    "sentiment": "negative",
                }
            ),
            rag(
                {
                    "query": "main complaints",
                    "sku_codes": [DELTA_2],
                    "week_range": {
                        "start_week_id": FIXTURE_WEEK,
                        "end_week_id": FIXTURE_WEEK,
                    },
                    "sentiment": "negative",
                    "top_k": 5,
                }
            ),
        ),
        'Noise leads with 7 fixture mentions; one example says "{quote}."',
        expected_citations=1,
    ),
    GoldenCase(
        "Q12",
        "combined",
        "Why did Delta 2 negativity rise across the fixture weeks?",
        (
            sql(
                {
                    "operation": "trend",
                    "sku_codes": [DELTA_2],
                    "week_range": FIXTURE_RANGE,
                    "sentiment": "negative",
                }
            ),
            rag(
                {
                    "query": "reasons for increased negativity",
                    "sku_codes": [DELTA_2],
                    "week_range": FIXTURE_RANGE,
                    "sentiment": "negative",
                    "top_k": 5,
                }
            ),
        ),
        'Negativity rises from 25% to 50%; retrieved context includes "{quote}."',
        expected_citations=1,
    ),
    GoldenCase(
        "Q13",
        "combined",
        "Which complaint category is most common, and show a representative comment?",
        (
            sql(
                {
                    "operation": "aspect_distribution",
                    "sku_codes": [DELTA_2],
                    "sentiment": "negative",
                }
            ),
            rag(
                {
                    "query": "representative complaint",
                    "sku_codes": [DELTA_2],
                    "sentiment": "negative",
                    "aspect_label": "noise_level",
                    "top_k": 3,
                }
            ),
        ),
        'Noise is the fixture leader with 7 mentions; a comment says "{quote}."',
        expected_citations=1,
    ),
    GoldenCase(
        "Q14",
        "follow_up",
        "What about noise specifically?",
        (
            sql(
                {
                    "operation": "compare_skus",
                    "sku_codes": [DELTA_2, JACKERY_1000],
                    "aspect_label": "noise_level",
                    "comparison_metric": "negative_rate",
                }
            ),
        ),
        "For the two previously named SKUs, fixture noise negativity is 50% versus 25%.",
        recent_messages=(
            ConversationMessage(
                role="user",
                content="Compare Delta 2 and Jackery Explorer 1000.",
            ),
            ConversationMessage(
                role="assistant",
                content="I can compare those same-tier SKUs using deterministic metrics.",
            ),
        ),
    ),
    GoldenCase(
        "Q15",
        "follow_up",
        "Show me some actual comments.",
        (
            rag(
                {
                    "query": "noise comments",
                    "sku_codes": [DELTA_2, JACKERY_1000],
                    "aspect_label": "noise_level",
                    "top_k": 5,
                }
            ),
        ),
        'For the same products and topic, a retrieved comment says "{quote}."',
        expected_citations=1,
        recent_messages=(
            ConversationMessage(
                role="user",
                content="Compare Delta 2 and Jackery Explorer 1000.",
            ),
            ConversationMessage(
                role="assistant",
                content="Delta 2 and Jackery 1000 are the active comparison.",
            ),
            ConversationMessage(role="user", content="What about noise specifically?"),
            ConversationMessage(
                role="assistant",
                content="Noise is now the active topic in the visible conversation.",
            ),
        ),
    ),
    GoldenCase(
        "Q16",
        "no_data",
        "Show Delta 2 complaints about an unsupported fixture aspect in week 202403.",
        (
            rag(
                {
                    "query": "unsupported fixture issue",
                    "sku_codes": [DELTA_2],
                    "week_range": {
                        "start_week_id": FIXTURE_WEEK,
                        "end_week_id": FIXTURE_WEEK,
                    },
                    "top_k": 5,
                },
                outcome="empty",
            ),
        ),
        "General product knowledge would speculate about this issue.",
        expected_status=AgentStatus.ABSTAINED,
    ),
    GoldenCase(
        "Q17",
        "no_data",
        "Find positive Delta 2 noise evidence in fixture week 202403 with strict filters.",
        (
            rag(
                {
                    "query": "positive quiet operation",
                    "sku_codes": [DELTA_2],
                    "week_range": {
                        "start_week_id": FIXTURE_WEEK,
                        "end_week_id": FIXTURE_WEEK,
                    },
                    "sentiment": "positive",
                    "aspect_label": "noise_level",
                    "top_k": 3,
                },
                outcome="empty",
            ),
        ),
        "General knowledge suggests the unit is quiet.",
        expected_status=AgentStatus.ABSTAINED,
    ),
    GoldenCase(
        "Q18",
        "failure_fallback",
        "Count Delta 2 complaints and show examples while evidence search is unavailable.",
        (
            sql(
                {
                    "operation": "review_count",
                    "sku_codes": [DELTA_2],
                    "sentiment": "negative",
                }
            ),
            rag(
                {
                    "query": "complaint examples",
                    "sku_codes": [DELTA_2],
                    "sentiment": "negative",
                    "top_k": 5,
                },
                outcome="rag_unavailable",
            ),
        ),
        "The fixture has 12 negative mentions; exact examples are unavailable.",
        expected_status=AgentStatus.PARTIAL,
        notes="Analytics remains usable; no citation is emitted.",
    ),
    GoldenCase(
        "Q19",
        "failure_fallback",
        "Summarize Delta 2 fixture week 202403 when no stored report exists.",
        (
            report(
                {"sku_code": DELTA_2, "week_id": FIXTURE_WEEK},
                outcome="not_found",
            ),
            sql(
                {
                    "operation": "review_count",
                    "sku_codes": [DELTA_2],
                    "week_range": {
                        "start_week_id": FIXTURE_WEEK,
                        "end_week_id": FIXTURE_WEEK,
                    },
                }
            ),
        ),
        "No stored report exists; deterministic analytics found 12 mentions across 8 reviews.",
        notes="Report remains read-only; fallback is Router-selected analytics.",
    ),
)


def _comparison_metrics(sku_code: str, negative_rate: float) -> SkuComparisonMetrics:
    negative_count = round(20 * negative_rate)
    return SkuComparisonMetrics(
        sku_code=sku_code,
        review_count=8 if sku_code == JACKERY_1000 else 24,
        mention_count=20,
        positive_count=20 - negative_count,
        negative_count=negative_count,
        neutral_count=0,
        positive_rate=1 - negative_rate,
        negative_rate=negative_rate,
        neutral_rate=0,
        sentiment_score=1 - (2 * negative_rate),
    )


def _trend_payload(operation: AnalyticsOperation, aspect_label: str | None) -> TrendPayload:
    return TrendPayload(
        operation=operation.value,
        aspect_label=aspect_label,
        points=[
            TrendPoint(
                week_id=202402,
                review_count=8,
                mention_count=8,
                positive_count=6,
                negative_count=2,
                neutral_count=0,
                positive_rate=0.75,
                negative_rate=0.25,
                neutral_rate=0,
            ),
            TrendPoint(
                week_id=202403,
                review_count=8,
                mention_count=8,
                positive_count=4,
                negative_count=4,
                neutral_count=0,
                positive_rate=0.5,
                negative_rate=0.5,
                neutral_rate=0,
            ),
        ],
    )


def _analytics_payload(arguments: AnalyticsToolArguments) -> Any:
    if arguments.operation is AnalyticsOperation.REVIEW_COUNT:
        return ReviewCountPayload(
            review_count=8,
            mention_count=12,
            by_sku=[
                SkuSampleCount(
                    sku_code=arguments.sku_codes[0],
                    review_count=8,
                    mention_count=12,
                )
            ],
        )
    if arguments.operation is AnalyticsOperation.ASPECT_DISTRIBUTION:
        return AspectDistributionPayload(
            mention_count=12,
            distribution=[
                AspectBucket(
                    aspect_label="noise_level",
                    mention_count=7,
                    proportion=7 / 12,
                    positive_count=0,
                    negative_count=7,
                    neutral_count=0,
                ),
                AspectBucket(
                    aspect_label="charging_experience",
                    mention_count=5,
                    proportion=5 / 12,
                    positive_count=0,
                    negative_count=5,
                    neutral_count=0,
                ),
            ],
        )
    if arguments.operation in {AnalyticsOperation.TREND, AnalyticsOperation.ASPECT_TREND}:
        return _trend_payload(arguments.operation, arguments.aspect_label)
    if arguments.operation is AnalyticsOperation.COMPARE_SKUS:
        return SkuComparisonPayload(
            capacity_tier="mid",
            comparison_metric=arguments.comparison_metric or ComparisonMetric.NEGATIVE_RATE,
            skus=[
                _comparison_metrics(arguments.sku_codes[0], 0.5),
                _comparison_metrics(arguments.sku_codes[1], 0.25),
            ],
        )
    raise AssertionError(f"golden fixture does not support {arguments.operation}")


class GoldenExecutor:
    def __init__(self, case: GoldenCase) -> None:
        self._case = case
        self._outcomes = {call.tool_name: call.outcome for call in case.calls}

    async def execute_sql(self, arguments: AnalyticsToolArguments) -> AnalyticsToolResult:
        outcome = self._outcomes[ToolName.SQL]
        if outcome == "capacity_tier_mismatch":
            return AnalyticsToolResult(
                status=ToolStatus.ERROR,
                tool_name=ToolName.SQL,
                normalized_args=arguments,
                execution=ToolExecutionMetadata(duration_ms=4, result_count=0),
                error=ToolError(
                    code="capacity_tier_mismatch",
                    message="Direct SKU comparison requires the same capacity tier.",
                    details={DELTA_2: "mid", ANKER_F2000: "large"},
                ),
            )
        warnings = []
        if outcome == "small_sample":
            warnings.append(
                ToolWarning(
                    code="small_sample",
                    message=SMALL_SAMPLE_MESSAGE,
                    details={
                        "sku_code": JACKERY_1000,
                        "sample_size": 8,
                        "threshold": 20,
                    },
                )
            )
        return AnalyticsToolResult(
            status=ToolStatus.SUCCESS,
            tool_name=ToolName.SQL,
            normalized_args=arguments,
            warnings=warnings,
            execution=ToolExecutionMetadata(duration_ms=4, result_count=1),
            payload=_analytics_payload(arguments),
        )

    async def execute_rag(self, arguments: RagToolArguments) -> RagToolResult:
        outcome = self._outcomes[ToolName.RAG]
        if outcome == "empty":
            return RagToolResult(
                status=ToolStatus.EMPTY,
                tool_name=ToolName.RAG,
                normalized_args=arguments,
                execution=ToolExecutionMetadata(duration_ms=3, result_count=0),
            )
        if outcome == "rag_unavailable":
            return RagToolResult(
                status=ToolStatus.ERROR,
                tool_name=ToolName.RAG,
                normalized_args=arguments,
                execution=ToolExecutionMetadata(duration_ms=3, result_count=0),
                error=ToolError(
                    code="rag_vector_search_failed",
                    message="Semantic evidence search is temporarily unavailable.",
                    retryable=True,
                ),
            )
        evidence = self.evidence
        return RagToolResult(
            status=ToolStatus.SUCCESS,
            tool_name=ToolName.RAG,
            normalized_args=arguments,
            execution=ToolExecutionMetadata(duration_ms=3, result_count=1),
            payload=RagRetrievalPayload(
                query=arguments.query,
                retrieved_count=1,
                evidence=[evidence],
            ),
        )

    async def execute_report(self, arguments: ReportToolArguments) -> ReportToolResult:
        outcome = self._outcomes[ToolName.REPORT]
        if outcome == "not_found":
            return ReportToolResult(
                status=ToolStatus.NOT_FOUND,
                tool_name=ToolName.REPORT,
                normalized_args=arguments,
                execution=ToolExecutionMetadata(duration_ms=2, result_count=0),
            )
        return ReportToolResult(
            status=ToolStatus.SUCCESS,
            tool_name=ToolName.REPORT,
            normalized_args=arguments,
            execution=ToolExecutionMetadata(duration_ms=2, result_count=1),
            payload=WeeklyReportPayload(
                report_id=uuid5(NAMESPACE_URL, f"{self._case.case_id}:report"),
                sku_code=arguments.sku_code,
                week_id=arguments.week_id,
                report_md="# Deterministic stored report",
                summary="Deterministic stored summary",
                generated_at=datetime(2024, 1, 25, tzinfo=UTC),
            ),
        )

    @property
    def evidence(self) -> RetrievedEvidence:
        rag_call = next(
            (call for call in self._case.calls if call.tool_name is ToolName.RAG),
            None,
        )
        arguments = (
            RagToolArguments.model_validate(rag_call.arguments)
            if rag_call is not None
            else RagToolArguments(query="fixture evidence", sku_codes=[DELTA_2])
        )
        mention_id = uuid5(NAMESPACE_URL, f"{self._case.case_id}:mention")
        document_id = uuid5(NAMESPACE_URL, f"{self._case.case_id}:document")
        aspect_label = arguments.aspect_label or "noise_level"
        mention_text = (
            "charging is inconsistent under load"
            if aspect_label == "charging_experience"
            else EVIDENCE_QUOTE
        )
        return RetrievedEvidence(
            mention_id=mention_id,
            document_id=document_id,
            sku_code=arguments.sku_codes[0],
            aspect_label=aspect_label,
            sentiment=arguments.sentiment or Sentiment.NEGATIVE,
            week_id=FIXTURE_WEEK,
            mention_text=mention_text,
            context_window=f"During charging, {mention_text} in a small room.",
            quality_score=0.84,
            similarity_score=0.92,
            source=ExpandedSourceMetadata(
                document_id=document_id,
                sku_code=arguments.sku_codes[0],
                platform="fixture",
                published_at=datetime(2024, 1, 17, tzinfo=UTC),
                source_url="https://example.test/golden-review",
                title="Deterministic golden review",
                rating=2,
                review_text=f"During charging, {mention_text} in a small room.",
            ),
        )


class GoldenModel:
    def __init__(self, case: GoldenCase, evidence: RetrievedEvidence) -> None:
        self._responses = [
            ModelResponse(
                tool_calls=[
                    ModelToolCall(
                        call_id=f"{case.case_id}-call-{index}",
                        name=call.tool_name.value,
                        arguments=call.arguments,
                    )
                ]
            )
            for index, call in enumerate(case.calls, start=1)
        ]
        self._responses.append(
            ModelResponse(
                content=case.answer.format(quote=evidence.mention_text),
                cited_evidence_ids=(
                    [str(evidence.mention_id)] if case.expected_citations else []
                ),
            )
        )
        self.calls: list[dict[str, Any]] = []

    async def complete(self, *, messages, tools) -> ModelResponse:
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        if not self._responses:
            raise AssertionError("golden model received an unexpected extra round")
        return self._responses.pop(0)


def _binding(
    name: ToolName,
    argument_model: type[AgentSchema],
    executor,
) -> ToolBinding:
    return ToolBinding(
        name=name,
        description=f"Golden acceptance binding for {name.value}",
        argument_model=argument_model,
        executor=executor,
    )


def _normalized_arguments(call: GoldenCall) -> dict[str, Any]:
    models = {
        ToolName.SQL: AnalyticsToolArguments,
        ToolName.RAG: RagToolArguments,
        ToolName.REPORT: ReportToolArguments,
    }
    return models[call.tool_name].model_validate(call.arguments).model_dump(mode="json")


def test_golden_catalog_has_the_locked_phase_10_composition() -> None:
    assert len(GOLDEN_CASES) == 19
    assert len({case.case_id for case in GOLDEN_CASES}) == 19
    assert Counter(case.category for case in GOLDEN_CASES) == {
        "count_distribution": 2,
        "trend": 2,
        "comparison": 3,
        "evidence": 3,
        "combined": 3,
        "follow_up": 2,
        "no_data": 2,
        "failure_fallback": 2,
    }
    assert all(1 <= len(case.calls) <= MAX_TOOL_CALLS for case in GOLDEN_CASES)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda case: case.case_id)
async def test_week3_golden_query(case: GoldenCase) -> None:
    executor = GoldenExecutor(case)
    model = GoldenModel(case, executor.evidence)
    router = FunctionCallingRouter(
        model,
        [
            _binding(ToolName.REPORT, ReportToolArguments, executor.execute_report),
            _binding(ToolName.SQL, AnalyticsToolArguments, executor.execute_sql),
            _binding(ToolName.RAG, RagToolArguments, executor.execute_rag),
        ],
        system_policy=VOC_SYSTEM_POLICY,
    )

    result = await router.run(
        recent_messages=case.recent_messages,
        current_user_message=case.query,
    )

    assert result.status is case.expected_status
    assert [trace.tool_name for trace in result.tool_trace] == [
        call.tool_name.value for call in case.calls
    ]
    assert [trace.arguments for trace in result.tool_trace] == [
        call.arguments for call in case.calls
    ]
    assert [trace.normalized_arguments for trace in result.tool_trace] == [
        _normalized_arguments(call) for call in case.calls
    ]
    assert result.execution.attempted_tool_call_count == len(case.calls)
    assert result.execution.executed_tool_call_count == len(case.calls)
    assert result.execution.attempted_tool_call_count <= MAX_TOOL_CALLS
    assert all(trace.duration_ms is not None for trace in result.tool_trace)
    assert len(result.citations) == case.expected_citations
    assert tuple(warning.code for warning in result.warnings) == (
        case.expected_warning_codes
    )
    assert all(
        citation.mention_id == executor.evidence.mention_id
        for citation in result.citations
    )
    for call in (item for item in case.calls if item.tool_name is ToolName.RAG):
        arguments = RagToolArguments.model_validate(call.arguments)
        evidence = executor.evidence
        assert evidence.sku_code in arguments.sku_codes
        if arguments.aspect_label is not None:
            assert evidence.aspect_label == arguments.aspect_label
        if arguments.sentiment is not None:
            assert evidence.sentiment is arguments.sentiment
    if case.expected_warning_codes:
        assert SMALL_SAMPLE_MESSAGE in result.final_answer
    if case.expected_status is AgentStatus.ABSTAINED:
        assert result.final_answer == NO_DATA_ANSWER
        assert "General" not in result.final_answer
    if case.case_id == "Q07":
        assert "Direct SKU comparison requires the same capacity tier." in (
            result.final_answer
        )
        assert "winner" not in result.final_answer.lower()
    if case.case_id == "Q18":
        assert "Semantic evidence search is temporarily unavailable." in (
            result.final_answer
        )
        assert result.citations == []
    if case.recent_messages:
        initial_messages = model.calls[0]["messages"]
        assert initial_messages[1 : 1 + len(case.recent_messages)] == [
            message.model_dump(mode="json") for message in case.recent_messages
        ]
