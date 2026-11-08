import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.agent.llm import ModelResponse, ModelToolCall
from backend.app.agent.router import FunctionCallingRouter, ToolBinding
from backend.app.agent.schemas import (
    AgentSchema,
    AgentStatus,
    AnalyticsOperation,
    AnalyticsToolArguments,
    ConversationMessage,
    ExpandedSourceMetadata,
    RagRetrievalPayload,
    RagToolArguments,
    RagToolResult,
    ReportToolArguments,
    ReportToolResult,
    RetrievedEvidence,
    ReviewCountPayload,
    SkuSampleCount,
    ToolError,
    ToolName,
    ToolResult,
    ToolStatus,
    ToolWarning,
    WeeklyReportPayload,
)


class ScriptedModel:
    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, *, messages, tools) -> ModelResponse:
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        if not self.responses:
            raise AssertionError("router requested an unexpected model response")
        return self.responses.pop(0)


class FailingModel:
    async def complete(self, *, messages, tools) -> ModelResponse:
        raise TimeoutError("provider timeout")


class RecordingExecutor:
    def __init__(self, results: Sequence[ToolResult[Any, Any]]) -> None:
        self.results = list(results)
        self.calls: list[AgentSchema] = []

    async def __call__(self, arguments: AgentSchema) -> ToolResult[Any, Any]:
        self.calls.append(arguments)
        if not self.results:
            raise AssertionError("tool was executed more times than expected")
        return self.results.pop(0)


def binding(
    name: ToolName,
    argument_model: type[AgentSchema],
    executor: RecordingExecutor,
) -> ToolBinding:
    return ToolBinding(
        name=name,
        description=f"approved {name.value}",
        argument_model=argument_model,
        executor=executor,
    )


def tool_call(
    call_id: str, name: ToolName, arguments: dict[str, Any] | str
) -> ModelResponse:
    return ModelResponse(
        tool_calls=[
            ModelToolCall(call_id=call_id, name=name.value, arguments=arguments)
        ]
    )


def final(answer: str, cited_ids: Sequence[UUID] = ()) -> ModelResponse:
    return ModelResponse(
        content=answer,
        cited_evidence_ids=[str(item) for item in cited_ids],
    )


def sql_result(
    *,
    status: ToolStatus = ToolStatus.SUCCESS,
    warnings: Sequence[ToolWarning] = (),
    error: ToolError | None = None,
    review_count: int = 12,
    mention_count: int = 20,
) -> ToolResult[Any, Any]:
    arguments = AnalyticsToolArguments(
        operation=AnalyticsOperation.REVIEW_COUNT,
        sku_codes=["ecoflow-delta2"],
    )
    payload = None
    if status is not ToolStatus.ERROR:
        payload = ReviewCountPayload(
            review_count=review_count,
            mention_count=mention_count,
            by_sku=[
                SkuSampleCount(
                    sku_code="ecoflow-delta2",
                    review_count=review_count,
                    mention_count=mention_count,
                )
            ],
        )
    return ToolResult[AnalyticsToolArguments, ReviewCountPayload](
        status=status,
        tool_name=ToolName.SQL,
        normalized_args=arguments,
        warnings=list(warnings),
        payload=payload,
        error=error,
    )


def evidence_item(
    *, mention_id: UUID | None = None, mention_text: str = "the fan is very loud"
) -> RetrievedEvidence:
    document_id = uuid4()
    return RetrievedEvidence(
        mention_id=mention_id or uuid4(),
        document_id=document_id,
        sku_code="ecoflow-delta2",
        aspect_label="noise_level",
        sentiment="negative",
        week_id=202635,
        mention_text=mention_text,
        context_window="At high load, the fan is very loud in a small room.",
        quality_score=0.8,
        similarity_score=0.9,
        source=ExpandedSourceMetadata(
            document_id=document_id,
            sku_code="ecoflow-delta2",
            platform="amazon",
            published_at=datetime(2026, 8, 25, tzinfo=UTC),
            review_text="At high load, the fan is very loud in a small room.",
        ),
    )


def rag_result(
    evidence: Sequence[RetrievedEvidence] = (),
    *,
    status: ToolStatus | None = None,
    error: ToolError | None = None,
) -> RagToolResult:
    resolved_status = status or (ToolStatus.SUCCESS if evidence else ToolStatus.EMPTY)
    payload = (
        RagRetrievalPayload(
            query="fan noise", retrieved_count=len(evidence), evidence=list(evidence)
        )
        if evidence
        else None
    )
    return RagToolResult(
        status=resolved_status,
        tool_name=ToolName.RAG,
        normalized_args=RagToolArguments(
            query="fan noise", sku_codes=["ecoflow-delta2"]
        ),
        payload=payload,
        error=error,
    )


def report_result(*, found: bool) -> ReportToolResult:
    arguments = ReportToolArguments(sku_code="ecoflow-delta2", week_id=202635)
    return ReportToolResult(
        status=ToolStatus.SUCCESS if found else ToolStatus.NOT_FOUND,
        tool_name=ToolName.REPORT,
        normalized_args=arguments,
        payload=(
            WeeklyReportPayload(
                report_id=uuid4(),
                sku_code="ecoflow-delta2",
                week_id=202635,
                report_md="# Stored weekly report",
                summary="Stored summary",
                generated_at=datetime(2026, 8, 26, tzinfo=UTC),
            )
            if found
            else None
        ),
    )


async def run_router(model: ScriptedModel, bindings: Sequence[ToolBinding]):
    return await FunctionCallingRouter(
        model, bindings, system_policy="Answer the current VOC request."
    ).run(
        recent_messages=[
            ConversationMessage(role="assistant", content="Which SKU should I inspect?")
        ],
        current_user_message="Use Delta 2.",
    )


@pytest.mark.asyncio
async def test_sql_only_question() -> None:
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            tool_call(
                "sql-1",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("Delta 2 has 12 matching reviews."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )

    assert result.status is AgentStatus.SUCCESS
    assert [item.tool_name for item in result.tool_trace] == ["tool_sql"]
    assert result.execution.executed_tool_call_count == 1
    assert model.calls[0]["messages"][-2:] == [
        {"role": "assistant", "content": "Which SKU should I inspect?"},
        {"role": "user", "content": "Use Delta 2."},
    ]
    policy = model.calls[0]["messages"][0]["content"]
    assert "Quantitative claims" in policy
    assert "Keep product comparisons neutral" in policy
    assert "Do not reveal chain-of-thought" in policy


@pytest.mark.asyncio
async def test_tool_lifecycle_events_bracket_actual_execution() -> None:
    ordering: list[str] = []

    async def execute(arguments: AgentSchema) -> ToolResult[Any, Any]:
        ordering.append("executor")
        return sql_result()

    async def capture(event) -> None:
        ordering.append(event.event_type)

    model = ScriptedModel(
        [
            tool_call(
                "sql-live",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("Delta 2 has matching reviews."),
        ]
    )
    router = FunctionCallingRouter(
        model,
        [
            ToolBinding(
                name=ToolName.SQL,
                description="approved tool_sql",
                argument_model=AnalyticsToolArguments,
                executor=execute,
            )
        ],
        system_policy="Answer the current VOC request.",
    )

    result = await router.run(
        recent_messages=[],
        current_user_message="Count Delta 2 reviews.",
        event_sink=capture,
    )

    assert result.status is AgentStatus.SUCCESS
    assert ordering == ["tool_started", "executor", "tool_completed"]


@pytest.mark.asyncio
async def test_rag_only_returns_only_actually_used_citation() -> None:
    used = evidence_item()
    unused = evidence_item(mention_text="charging is slower than expected")
    executor = RecordingExecutor([rag_result([used, unused])])
    model = ScriptedModel(
        [
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            final(f'One review says "{used.mention_text}."', [used.mention_id]),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.RAG, RagToolArguments, executor)]
    )

    assert result.status is AgentStatus.SUCCESS
    assert [item.mention_id for item in result.citations] == [used.mention_id]
    tool_message = next(
        message for message in model.calls[1]["messages"] if message["role"] == "tool"
    )
    assert used.mention_text in tool_message["content"]
    assert "review_text" not in tool_message["content"]


@pytest.mark.asyncio
async def test_rag_exact_quote_without_citation_gets_one_json_correction_round() -> (
    None
):
    used = evidence_item()
    unused = evidence_item(mention_text="charging is slower than expected")
    executor = RecordingExecutor([rag_result([used, unused])])
    model = ScriptedModel(
        [
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            final(f'One review says "{used.mention_text}."'),
            final(f'One review says "{used.mention_text}."', [used.mention_id]),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.RAG, RagToolArguments, executor)]
    )

    assert result.status is AgentStatus.SUCCESS
    assert [item.mention_id for item in result.citations] == [used.mention_id]
    assert unused.mention_id not in [item.mention_id for item in result.citations]
    assert model.calls[2]["tools"] == []
    correction = model.calls[2]["messages"][-1]["content"]
    assert str(used.mention_id) in correction
    assert str(unused.mention_id) in correction
    assert result.execution.attempted_tool_call_count == 1
    assert result.execution.executed_tool_call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("correction_mode", ["unknown", "empty", "non_json"])
async def test_invalid_citation_correction_remains_a_controlled_failure(
    correction_mode: str,
) -> None:
    evidence = evidence_item()
    executor = RecordingExecutor([rag_result([evidence])])
    if correction_mode == "unknown":
        corrected = final(f'One review says "{evidence.mention_text}."', [uuid4()])
    elif correction_mode == "empty":
        corrected = final(f'One review says "{evidence.mention_text}."')
    else:
        corrected = ModelResponse(content=f'One review says "{evidence.mention_text}."')
    model = ScriptedModel(
        [
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            final(f'One review says "{evidence.mention_text}."'),
            corrected,
        ]
    )

    result = await run_router(
        model, [binding(ToolName.RAG, RagToolArguments, executor)]
    )

    assert result.status is AgentStatus.ERROR
    assert result.citations == []
    assert model.calls[2]["tools"] == []
    assert result.execution.attempted_tool_call_count == 1
    assert result.execution.executed_tool_call_count == 1


@pytest.mark.asyncio
async def test_rag_answer_without_exact_evidence_does_not_trigger_citation_correction() -> (
    None
):
    evidence = evidence_item()
    executor = RecordingExecutor([rag_result([evidence])])
    model = ScriptedModel(
        [
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("The retrieved VOC result supports a qualitative summary."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.RAG, RagToolArguments, executor)]
    )

    assert result.status is AgentStatus.SUCCESS
    assert result.citations == []
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_sql_then_rag_multi_tool_synthesis() -> None:
    evidence = evidence_item()
    sql_executor = RecordingExecutor([sql_result()])
    rag_executor = RecordingExecutor([rag_result([evidence])])
    model = ScriptedModel(
        [
            tool_call(
                "sql-1",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            final(
                f'There are 12 reviews; one says "{evidence.mention_text}."',
                [evidence.mention_id],
            ),
        ]
    )

    result = await run_router(
        model,
        [
            binding(ToolName.SQL, AnalyticsToolArguments, sql_executor),
            binding(ToolName.RAG, RagToolArguments, rag_executor),
        ],
    )

    assert result.status is AgentStatus.SUCCESS
    assert [item.tool_name for item in result.tool_trace] == ["tool_sql", "tool_rag"]
    assert len(result.citations) == 1


@pytest.mark.asyncio
async def test_report_hit_stops_without_fallback() -> None:
    executor = RecordingExecutor([report_result(found=True)])
    model = ScriptedModel(
        [
            tool_call(
                "report-1",
                ToolName.REPORT,
                {"sku_code": "ecoflow-delta2", "week_id": 202635},
            ),
            final("The stored report summary is available."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.REPORT, ReportToolArguments, executor)]
    )

    assert result.status is AgentStatus.SUCCESS
    assert len(result.tool_trace) == 1


@pytest.mark.asyncio
async def test_report_miss_can_fall_back_to_analytics() -> None:
    report_executor = RecordingExecutor([report_result(found=False)])
    sql_executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            tool_call(
                "report-1",
                ToolName.REPORT,
                {"sku_code": "ecoflow-delta2", "week_id": 202635},
            ),
            tool_call(
                "sql-1",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("No stored report exists; analytics found 12 reviews."),
        ]
    )

    result = await run_router(
        model,
        [
            binding(ToolName.REPORT, ReportToolArguments, report_executor),
            binding(ToolName.SQL, AnalyticsToolArguments, sql_executor),
        ],
    )

    assert result.status is AgentStatus.SUCCESS
    assert [item.status for item in result.tool_trace] == [
        ToolStatus.NOT_FOUND,
        ToolStatus.SUCCESS,
    ]


@pytest.mark.asyncio
async def test_report_miss_reprompts_before_allowing_an_unsupported_final_answer() -> (
    None
):
    report_executor = RecordingExecutor([report_result(found=False)])
    sql_executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            tool_call(
                "report-1",
                ToolName.REPORT,
                {"sku_code": "ecoflow-delta2", "week_id": 202635},
            ),
            final("No stored report exists."),
            tool_call(
                "sql-1",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("No stored report exists; analytics found 12 reviews."),
        ]
    )

    result = await run_router(
        model,
        [
            binding(ToolName.REPORT, ReportToolArguments, report_executor),
            binding(ToolName.SQL, AnalyticsToolArguments, sql_executor),
        ],
    )

    assert result.status is AgentStatus.SUCCESS
    assert [trace.tool_name for trace in result.tool_trace] == [
        ToolName.REPORT.value,
        ToolName.SQL.value,
    ]
    assert "stored report was not found" in model.calls[2]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_unsupported_first_round_answer_is_reprompted_for_grounding() -> None:
    sql_executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            final("I can answer without using a tool."),
            tool_call(
                "sql-1",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("The grounded answer uses 12 reviews."),
        ]
    )

    result = await run_router(
        model,
        [binding(ToolName.SQL, AnalyticsToolArguments, sql_executor)],
    )

    assert result.status is AgentStatus.SUCCESS
    assert result.execution.model_round_count == 3
    assert [trace.tool_name for trace in result.tool_trace] == [ToolName.SQL.value]
    assert "No approved tool result" in model.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,answer",
    [
        ("你好", "你好，我可以帮助你分析客户反馈。"),
        ("你能做什么", "我可以查询反馈数量、分析情绪、比较产品并查找原文例子。"),
        ("怎么使用", "可以告诉我你关心的产品和时间，以及想看统计还是客户原文。"),
        ("什么是VOC", "VOC是客户之声，用于了解客户的体验和需求。"),
        ("帮我比较", "你希望比较哪些产品，关注哪个时间段？"),
    ],
)
async def test_general_guidance_succeeds_without_tool_calls(question, answer) -> None:
    executor = RecordingExecutor([])
    model = ScriptedModel(
        [ModelResponse(content=answer, answer_kind="general_guidance")]
    )
    result = await FunctionCallingRouter(
        model,
        [binding(ToolName.SQL, AnalyticsToolArguments, executor)],
        system_policy="",
    ).run(recent_messages=[], current_user_message=question)
    assert result.status is AgentStatus.SUCCESS
    assert result.final_answer == answer
    assert result.execution.model_round_count == 1
    assert result.execution.executed_tool_call_count == 0
    assert executor.calls == []
    assert "Your available capabilities" in model.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_ungrounded_data_answer_is_still_blocked() -> None:
    model = ScriptedModel([final("There are 12 reviews.")] * 2)
    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, RecordingExecutor([]))]
    )
    assert result.status is AgentStatus.ERROR
    assert "No successful tool result" in result.final_answer


@pytest.mark.asyncio
async def test_guidance_label_does_not_bypass_failed_query() -> None:
    executor = RecordingExecutor(
        [
            sql_result(
                status=ToolStatus.ERROR,
                error=ToolError(
                    code="analytics_query_failed", message="Database unavailable"
                ),
            )
        ]
    )
    model = ScriptedModel(
        [
            tool_call("sql-1", ToolName.SQL, {"operation": "review_count"}),
            ModelResponse(
                content="There are 12 reviews.", answer_kind="general_guidance"
            ),
        ]
    )
    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )
    assert result.status is AgentStatus.ERROR


@pytest.mark.asyncio
async def test_guidance_cannot_cite_unretrieved_evidence() -> None:
    response = ModelResponse(
        content="A customer said this.",
        answer_kind="general_guidance",
        cited_evidence_ids=[str(uuid4())],
    )
    result = await run_router(
        ScriptedModel([response, response]),
        [binding(ToolName.SQL, AnalyticsToolArguments, RecordingExecutor([]))],
    )
    assert result.status is AgentStatus.ERROR


@pytest.mark.asyncio
async def test_plain_guidance_is_repaired_without_tools() -> None:
    model = ScriptedModel(
        [
            ModelResponse(content="你好", requires_formatting=True),
            ModelResponse(
                content="你好，我可以帮助你分析客户反馈。",
                answer_kind="general_guidance",
            ),
        ]
    )
    result = await run_router(
        model,
        [
            binding(ToolName.SQL, AnalyticsToolArguments, RecordingExecutor([])),
        ],
    )
    assert result.status is AgentStatus.SUCCESS
    assert result.execution.model_round_count == 2
    assert model.calls[0]["tools"]
    assert model.calls[1]["tools"] == []


@pytest.mark.asyncio
async def test_format_repair_targets_latest_question_in_multiturn_chat() -> None:
    question = "介绍使用方法和你的定位"
    model = ScriptedModel(
        [
            ModelResponse(
                content="你好，有什么可以帮助你的？", requires_formatting=True
            ),
            ModelResponse(
                content="我帮助你分析客户反馈。可以直接提出产品和想了解的问题。",
                answer_kind="general_guidance",
            ),
        ]
    )
    result = await FunctionCallingRouter(model, [], system_policy="").run(
        recent_messages=[
            ConversationMessage(role="user", content="你好"),
            ConversationMessage(role="assistant", content="你好，有什么可以帮助你的？"),
        ],
        current_user_message=question,
    )
    assert result.status is AgentStatus.SUCCESS
    repair = model.calls[1]["messages"]
    assert len(repair) == 2
    payload = json.loads(repair[-1]["content"])
    assert payload["current_user_message"] == question
    assert payload["draft_answer"] == "你好，有什么可以帮助你的？"


@pytest.mark.asyncio
async def test_format_repair_of_data_request_preserves_query_path() -> None:
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            ModelResponse(content="I need to query data.", requires_formatting=True),
            final("A query is needed."),
            tool_call("sql-1", ToolName.SQL, {"operation": "review_count"}),
            final("There are 12 reviews."),
        ]
    )
    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )
    assert result.status is AgentStatus.SUCCESS
    assert result.execution.model_round_count == 4
    assert model.calls[1]["tools"] == []
    assert model.calls[2]["tools"]
    assert len(executor.calls) == 1


@pytest.mark.asyncio
async def test_repeated_plain_answers_cannot_loop_or_bypass_grounding() -> None:
    model = ScriptedModel(
        [ModelResponse(content="There are 12 reviews.", requires_formatting=True)] * 3
    )
    result = await run_router(
        model,
        [
            binding(ToolName.SQL, AnalyticsToolArguments, RecordingExecutor([])),
        ],
    )
    assert result.status is AgentStatus.ERROR
    assert result.execution.model_round_count == 3


@pytest.mark.asyncio
async def test_provider_argument_aliases_are_normalized_before_strict_validation() -> (
    None
):
    sql_executor = RecordingExecutor([sql_result()])
    rag_executor = RecordingExecutor([rag_result([evidence_item()])])
    model = ScriptedModel(
        [
            tool_call(
                "sql-1",
                ToolName.SQL,
                {
                    "operation": "review_count",
                    "sku_code": "ecoflow-delta2",
                    "week_id": 202635,
                },
            ),
            tool_call(
                "rag-1",
                ToolName.RAG,
                {
                    "search_query": "fan noise",
                    "sku": "ecoflow-delta2",
                    "week": 202635,
                    "aspect": "noise_level",
                    "limit": 1,
                },
            ),
            final(
                "The supported answer.",
                [rag_executor.results[0].payload.evidence[0].mention_id],
            ),
        ]
    )

    result = await run_router(
        model,
        [
            binding(ToolName.SQL, AnalyticsToolArguments, sql_executor),
            binding(ToolName.RAG, RagToolArguments, rag_executor),
        ],
    )

    assert result.status is AgentStatus.SUCCESS
    assert sql_executor.calls[0].sku_codes == ["ecoflow-delta2"]
    assert sql_executor.calls[0].week_range is not None
    assert sql_executor.calls[0].week_range.start_week_id == 202635
    assert rag_executor.calls[0].query == "fan noise"
    assert rag_executor.calls[0].sku_codes == ["ecoflow-delta2"]
    assert rag_executor.calls[0].top_k == 1


@pytest.mark.asyncio
async def test_provider_argument_normalization_does_not_accept_unknown_fields() -> None:
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            tool_call(
                "sql-1",
                ToolName.SQL,
                {
                    "operation": "review_count",
                    "sku_code": "ecoflow-delta2",
                    "sql": "SELECT * FROM documents",
                },
            ),
            final("The query succeeded."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )

    assert result.status is AgentStatus.ERROR
    assert executor.calls == []
    assert result.tool_trace[0].error is not None
    assert result.tool_trace[0].error.code == "invalid_tool_arguments"


def test_provider_tool_schemas_are_flat_and_keep_required_contracts() -> None:
    executor = RecordingExecutor([])
    sql_schema = binding(ToolName.SQL, AnalyticsToolArguments, executor).definition()[
        "function"
    ]["parameters"]
    rag_schema = binding(ToolName.RAG, RagToolArguments, executor).definition()[
        "function"
    ]["parameters"]

    assert "$defs" not in sql_schema
    assert "anyOf" not in json.dumps(sql_schema)
    assert sql_schema["required"] == ["operation"]
    assert sql_schema["properties"]["operation"]["enum"] == [
        "review_count",
        "sentiment_distribution",
        "aspect_distribution",
        "trend",
        "aspect_trend",
        "compare_skus",
    ]
    assert "$defs" not in rag_schema
    assert "anyOf" not in json.dumps(rag_schema)
    assert rag_schema["required"] == ["query"]


@pytest.mark.asyncio
async def test_no_data_overrides_model_prior_knowledge_with_abstention() -> None:
    executor = RecordingExecutor([rag_result()])
    model = ScriptedModel(
        [
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "unknown issue", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("From general knowledge, the product probably behaves this way."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.RAG, RagToolArguments, executor)]
    )

    assert result.status is AgentStatus.ABSTAINED
    assert "does not provide sufficient evidence" in result.final_answer
    assert result.citations == []


@pytest.mark.asyncio
async def test_low_sample_warning_is_deterministically_surfaced() -> None:
    warning = ToolWarning(
        code="small_sample",
        message="Delta 2 has 5 reviews, below the threshold of 20.",
        details={"sample_size": 5, "threshold": 20},
    )
    executor = RecordingExecutor(
        [sql_result(warnings=[warning], review_count=5, mention_count=8)]
    )
    model = ScriptedModel(
        [
            tool_call(
                "sql-1",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("The matching count is 5."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )

    assert result.warnings == [warning]
    assert warning.message in result.final_answer


@pytest.mark.asyncio
async def test_cross_tier_constraint_is_surfaced_without_declaring_a_winner() -> None:
    constraint = ToolError(
        code="capacity_tier_mismatch",
        message="Direct SKU comparison requires the same capacity tier.",
        details={"ecoflow-delta2": "mid", "anker-solix-f2000": "large"},
    )
    executor = RecordingExecutor(
        [sql_result(status=ToolStatus.ERROR, error=constraint)]
    )
    model = ScriptedModel(
        [
            tool_call(
                "sql-1",
                ToolName.SQL,
                {
                    "operation": "compare_skus",
                    "sku_codes": ["ecoflow-delta2", "anker-solix-f2000"],
                },
            ),
            final("A direct comparison is not valid for these capacity tiers."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )

    assert result.status is AgentStatus.SUCCESS
    assert constraint.message in result.final_answer
    assert "winner" not in result.final_answer.lower()


@pytest.mark.asyncio
async def test_one_tool_failure_and_one_success_produces_disclosed_partial_answer() -> (
    None
):
    sql_error = ToolError(
        code="analytics_query_failed",
        message="Analytics data is temporarily unavailable.",
        retryable=True,
    )
    evidence = evidence_item()
    sql_executor = RecordingExecutor(
        [sql_result(status=ToolStatus.ERROR, error=sql_error)]
    )
    rag_executor = RecordingExecutor([rag_result([evidence])])
    model = ScriptedModel(
        [
            tool_call(
                "sql-1",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            final(
                f'Qualitative evidence says "{evidence.mention_text}."',
                [evidence.mention_id],
            ),
        ]
    )

    result = await run_router(
        model,
        [
            binding(ToolName.SQL, AnalyticsToolArguments, sql_executor),
            binding(ToolName.RAG, RagToolArguments, rag_executor),
        ],
    )

    assert result.status is AgentStatus.PARTIAL
    assert sql_error.message in result.final_answer
    assert len(result.citations) == 1


@pytest.mark.asyncio
async def test_milvus_failure_keeps_supported_analytics_partial_without_citations() -> (
    None
):
    rag_error = ToolError(
        code="rag_vector_search_failed",
        message="Semantic evidence search is temporarily unavailable.",
        retryable=True,
    )
    sql_executor = RecordingExecutor([sql_result()])
    rag_executor = RecordingExecutor(
        [rag_result(status=ToolStatus.ERROR, error=rag_error)]
    )
    model = ScriptedModel(
        [
            tool_call(
                "sql-1",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("Delta 2 has 12 matching reviews."),
        ]
    )

    result = await run_router(
        model,
        [
            binding(ToolName.SQL, AnalyticsToolArguments, sql_executor),
            binding(ToolName.RAG, RagToolArguments, rag_executor),
        ],
    )

    assert result.status is AgentStatus.PARTIAL
    assert result.citations == []
    assert rag_error.message in result.final_answer


@pytest.mark.asyncio
async def test_fourth_tool_call_is_not_executed_and_limit_is_recorded() -> None:
    sql_executor = RecordingExecutor([sql_result(), sql_result()])
    report_executor = RecordingExecutor([report_result(found=True)])
    rag_executor = RecordingExecutor([rag_result([evidence_item()])])
    model = ScriptedModel(
        [
            tool_call("sql-1", ToolName.SQL, {"operation": "review_count"}),
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            tool_call(
                "report-1",
                ToolName.REPORT,
                {"sku_code": "ecoflow-delta2", "week_id": 202635},
            ),
            tool_call(
                "sql-4",
                ToolName.SQL,
                {"operation": "trend", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("The available results support a limited synthesis."),
        ]
    )

    result = await run_router(
        model,
        [
            binding(ToolName.SQL, AnalyticsToolArguments, sql_executor),
            binding(ToolName.RAG, RagToolArguments, rag_executor),
            binding(ToolName.REPORT, ReportToolArguments, report_executor),
        ],
    )

    assert result.status is AgentStatus.PARTIAL
    assert result.execution.attempted_tool_call_count == 4
    assert result.execution.executed_tool_call_count == 3
    assert result.execution.limit_event is not None
    assert result.execution.limit_event.attempted_call_id == "sql-4"
    assert len(sql_executor.calls) == 1
    assert model.calls[-1]["tools"] == []


@pytest.mark.asyncio
async def test_malformed_arguments_return_controlled_failure_without_execution() -> (
    None
):
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            tool_call("sql-1", ToolName.SQL, {"operation": "execute_sql"}),
            final("The query succeeded."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )

    assert result.status is AgentStatus.ERROR
    assert executor.calls == []
    assert result.tool_trace[0].error is not None
    assert result.tool_trace[0].error.code == "invalid_tool_arguments"


@pytest.mark.asyncio
async def test_malformed_arguments_can_be_corrected_within_the_call_budget() -> None:
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            tool_call("sql-invalid", ToolName.SQL, {"operation": "execute_sql"}),
            tool_call(
                "sql-corrected",
                ToolName.SQL,
                {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]},
            ),
            final("Delta 2 has 12 matching reviews."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )

    assert result.status is AgentStatus.PARTIAL
    assert len(executor.calls) == 1
    assert result.execution.attempted_tool_call_count == 2
    assert result.tool_trace[0].error is not None
    assert result.tool_trace[0].error.code == "invalid_tool_arguments"
    assert "Tool arguments failed schema validation." in result.final_answer


@pytest.mark.asyncio
async def test_duplicate_call_is_not_reexecuted_or_looped_forever() -> None:
    arguments = {"operation": "review_count", "sku_codes": ["ecoflow-delta2"]}
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            tool_call("sql-1", ToolName.SQL, arguments),
            tool_call("sql-2", ToolName.SQL, arguments),
            final("The first analytics result is sufficient."),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.SQL, AnalyticsToolArguments, executor)]
    )

    assert result.status is AgentStatus.SUCCESS
    assert len(executor.calls) == 1
    assert result.execution.attempted_tool_call_count == 2
    assert result.tool_trace[1].executed is False
    assert result.tool_trace[1].error is not None
    assert result.tool_trace[1].error.code == "duplicate_tool_call"
    assert "reasoning" not in result.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize("citation_mode", ["unknown", "missing"])
async def test_final_answer_cannot_use_unverified_or_uncited_evidence(
    citation_mode: str,
) -> None:
    evidence = evidence_item()
    executor = RecordingExecutor([rag_result([evidence])])
    cited_ids = [uuid4()] if citation_mode == "unknown" else []
    model = ScriptedModel(
        [
            tool_call(
                "rag-1",
                ToolName.RAG,
                {"query": "fan noise", "sku_codes": ["ecoflow-delta2"]},
            ),
            final(f'A review says "{evidence.mention_text}."', cited_ids),
            final(f'A review says "{evidence.mention_text}."', cited_ids),
        ]
    )

    result = await run_router(
        model, [binding(ToolName.RAG, RagToolArguments, executor)]
    )

    assert result.status is AgentStatus.ERROR
    assert result.citations == []


@pytest.mark.asyncio
async def test_model_provider_failure_returns_controlled_structured_error() -> None:
    result = await FunctionCallingRouter(
        FailingModel(), [], system_policy="Answer the current VOC request."
    ).run(recent_messages=[], current_user_message="Count Delta 2 reviews.")

    assert result.status is AgentStatus.ERROR
    assert result.final_answer == "The language model is temporarily unavailable."
    assert result.error is not None
    assert result.error.code == "llm_timeout"
    assert "provider timeout" not in result.error.message
    assert result.execution.model_round_count == 1
    assert result.execution.executed_tool_call_count == 0


@pytest.mark.asyncio
async def test_product_request_cannot_escape_grounding_using_guidance_label():
    model = ScriptedModel(
        [ModelResponse(content="续航普遍很好", answer_kind="general_guidance")] * 8
    )
    result = await FunctionCallingRouter(
        model,
        [binding(ToolName.SQL, AnalyticsToolArguments, RecordingExecutor([]))],
        system_policy="",
    ).run(recent_messages=[], current_user_message="EcoFlow Delta 2有多少评论？")
    assert result.status is AgentStatus.ERROR
    assert result.execution.executed_tool_call_count == 1


@pytest.mark.asyncio
async def test_scope_is_applied_before_executor_receives_arguments():
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            tool_call(
                "scoped",
                ToolName.SQL,
                {
                    "operation": "review_count",
                    "sku_codes": ["jackery-explorer-1000"],
                    "week_range": {"start_week_id": 202313, "end_week_id": 202313},
                },
            ),
            final("有12条评论"),
        ]
    )
    result = await FunctionCallingRouter(
        model,
        [binding(ToolName.SQL, AnalyticsToolArguments, executor)],
        system_policy="",
    ).run(recent_messages=[], current_user_message="EcoFlow Delta 2有多少评论？")
    assert result.status is AgentStatus.SUCCESS
    assert executor.calls[0].sku_codes == ["ecoflow-delta2"]
    assert executor.calls[0].week_range is None


@pytest.mark.asyncio
async def test_mixed_request_cannot_report_full_success_after_omitting_retrieval():
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [tool_call("count", ToolName.SQL, {"operation": "review_count"})]
        + [final("有12条评论。续航尚无法判断。 ")] * 7
    )
    result = await FunctionCallingRouter(
        model,
        [binding(ToolName.SQL, AnalyticsToolArguments, executor)],
        system_policy="",
    ).run(recent_messages=[], current_user_message="Delta 2有多少评论，续航怎么样？")
    assert result.status is AgentStatus.PARTIAL
    assert any(w.code == "incomplete_request" for w in result.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", [True, False])
async def test_paraphrased_feedback_needs_verified_citation(repair):
    evidence = evidence_item()
    executor = RecordingExecutor([rag_result([evidence])])
    model = ScriptedModel(
        [
            tool_call("rag", ToolName.RAG, {"query": "user feedback"}),
            final("用户反馈存在噪声问题。"),
            final("用户反馈存在噪声问题。", [evidence.mention_id] if repair else []),
        ]
    )
    result = await FunctionCallingRouter(
        model, [binding(ToolName.RAG, RagToolArguments, executor)], system_policy=""
    ).run(recent_messages=[], current_user_message="Delta 2用户评价怎么样？")
    assert result.status is (AgentStatus.SUCCESS if repair else AgentStatus.ERROR)
    assert bool(result.citations) == repair


@pytest.mark.asyncio
async def test_count_recovery_uses_followup_scope_when_model_omits_query():
    executor = RecordingExecutor([sql_result()])
    model = ScriptedModel(
        [
            ModelResponse(content="请先查询", answer_kind="general_guidance"),
            final("有12条评论"),
        ]
    )
    result = await FunctionCallingRouter(
        model,
        [binding(ToolName.SQL, AnalyticsToolArguments, executor)],
        system_policy="",
    ).run(
        recent_messages=[
            ConversationMessage(role="user", content="EcoFlow Delta 2用户反馈")
        ],
        current_user_message="这些反馈对应多少条去重后的评论？请统计全部时间。",
    )
    assert result.status is AgentStatus.SUCCESS
    assert executor.calls[0].sku_codes == ["ecoflow-delta2"]
    assert executor.calls[0].operation is AnalyticsOperation.REVIEW_COUNT
