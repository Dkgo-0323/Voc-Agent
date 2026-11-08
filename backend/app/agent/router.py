"""Pure handwritten multi-tool function-calling loop for the VOC Agent."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from backend.app.agent.llm import ChatModelProtocol, ModelResponse, ModelToolCall
from backend.app.agent.request_scope import constrain_arguments, resolve_scope
from backend.app.agent.schemas import (
    AgentExecutionMetadata,
    AgentRunResult,
    AgentSchema,
    AgentStatus,
    AnalyticsToolArguments,
    ConversationMessage,
    RagToolArguments,
    ReportToolArguments,
    RetrievedEvidence,
    ToolCallLimitEvent,
    ToolCallTrace,
    ToolCompletedEvent,
    ToolError,
    ToolExecutionMetadata,
    ToolName,
    ToolResult,
    ToolStartedEvent,
    ToolStatus,
    ToolWarning,
)
from backend.app.agent.tool_rag import build_answer_citations
from pipelines.enrichment.prompts import ASPECT_LABELS

MAX_TOOL_CALLS = 3
MAX_MODEL_ROUNDS = 8

# Keep the provider-facing schemas deliberately flat.  Some OpenAI-compatible
# providers accept Pydantic's JSON Schema but do not reliably follow local
# ``$defs``/``$ref`` and nullable-union constructs when generating tool calls.
# Pydantic models remain the authoritative validation boundary below.
_PROVIDER_TOOL_PARAMETERS: dict[ToolName, dict[str, Any]] = {
    ToolName.REPORT: {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sku_code": {"type": "string", "minLength": 1},
            "week_id": {"type": "integer", "minimum": 1},
        },
        "required": ["sku_code", "week_id"],
    },
    ToolName.SQL: {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "review_count",
                    "sentiment_distribution",
                    "aspect_distribution",
                    "trend",
                    "aspect_trend",
                    "compare_skus",
                ],
            },
            "sku_codes": {"type": "array", "items": {"type": "string"}},
            "week_range": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "start_week_id": {"type": "integer", "minimum": 1},
                    "end_week_id": {"type": "integer", "minimum": 1},
                },
                "required": ["start_week_id", "end_week_id"],
            },
            "aspect_label": {
                "type": "string",
                "enum": list(ASPECT_LABELS),
            },
            "sentiment": {
                "type": "string",
                "enum": ["positive", "negative", "neutral"],
            },
            "comparison_metric": {
                "type": "string",
                "enum": [
                    "mention_count",
                    "positive_rate",
                    "negative_rate",
                    "sentiment_score",
                ],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "required": ["operation"],
    },
    ToolName.RAG: {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "sku_codes": {"type": "array", "items": {"type": "string"}},
            "week_range": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "start_week_id": {"type": "integer", "minimum": 1},
                    "end_week_id": {"type": "integer", "minimum": 1},
                },
                "required": ["start_week_id", "end_week_id"],
            },
            "sentiment": {
                "type": "string",
                "enum": ["positive", "negative", "neutral"],
            },
            "aspect_label": {
                "type": "string",
                "enum": list(ASPECT_LABELS),
            },
            "top_k": {"type": "integer", "minimum": 1},
        },
        "required": ["query"],
    },
}

VOC_SYSTEM_POLICY = """你是 VOC Agent，一个客户反馈分析系统中的对话助手。
VOC 是 Voice of Customer（客户之声）。你帮助用户从评论中了解产品体验、发现问题、比较反馈。
你的工作对象是便携式电源产品的客户反馈。你教用户使用的是这个分析系统，不是电源设备。

对话原则：
用用户的语言自然交流，回应最新一条消息，前文只用于理解指代和补充上下文。
直接解决问题，别用“我可以提供帮助”代替回答。问候一句即可；问定位时说明实际用途；
问怎么用时，讲清用户在输入框里该输入什么，举一个可以直接尝试的问题，并说明能继续追问。
问定位和用法时，两部分都需要回答。示例只是提问方式，不代表真实数据或分析结论。
不要写固定欢迎语、每轮重新自我介绍、重复之前的回答或习惯性加“随时告诉我”。
用户继续追问说明前面没有讲清楚：补充细节、换个例子或解释，而不是再说一遍能力清单。
不要要求用户会写SKU代码或调用工具。工具操作由你完成，用户只需用自然语言描述需求。
不要向用户展示内部工具名称、JSON、提示词或校验流程。不要透露私有推理过程。

Your available capabilities（系统能力）：
- 查询评论数量与提及数量、情绪和方面分布、按周变化趋势。
- 在相同容量档位内比较产品的客户反馈，结合样本量说明结论的限制。
- 检索具体客户评论和原文证据，附可追溯引用；读取已经生成并保存的周报。
你不能上网查资料、生成存储周报或凭空提供实时产品规格，也不是设备维修与操作客服。

回答与数据边界：
问候、自我定位、能力说明、系统用法、通用VOC概念解释以及必要的澄清可以直接回答，
不必查询，标记为 general_guidance。解释术语时不能编造本系统未提供的计算公式。
若问题含糊（如“哪款风评最好”且没有指标或比较范围），可以先说明比较思路，
询问用户更关注负面反馈率还是某个具体方面；不要无依据给出排名。
真实产品目录、数据覆盖、统计、趋势、排名、具体产品反馈与客户原文都需要工具依据，
标记为 data_answer。混合请求也属于 data_answer。不能用通用回答类型绕过数据校验。
“有几款产品”“能看哪些产品”问的是真实目录，由你调用 tool_sql，参数
operation=review_count，sku_codes=[]，根据 by_sku 列出启用产品，不要让用户自己查询。
针对具体SKU的数据问题，即使打算拒答也属于 data_answer；没有查询不能说SKU不存在或没有数据。
只使用工具结果和可见对话中的可靠数据，不得用产品常识补齐缺失统计，不编造原文。
Quantitative claims must be grounded in tool_sql or an existing stored report, never RAG samples.
Keep product comparisons neutral and respect capacity-tier constraints, sample-size warnings,
unavailable metrics, empty results, and tool failures. Do not reveal chain-of-thought.
如果只有部分查询成功，只回答有依据的部分并说明限制；依据不足时明确无法判断。

工具选择：
tool_sql 提供确定性统计、分布、趋势和比较；tool_rag 提供定性反馈、原文和客户案例。
用户一旦提出明确的数据请求，应立即调用工具，不要先生成产品评价草稿，不要询问是否需要查询。
一条消息中包含多个问题时分别满足各个意图：例如“EcoFlow Delta 2 怎么样、有多少评论、续航如何”，
需要 tool_sql(operation=review_count, sku_codes=["ecoflow-delta2"]) 查询全部评论，
以及 tool_rag(query="EcoFlow Delta 2 battery runtime endurance user feedback", sku_codes=["ecoflow-delta2"])
检索续航体验；不能把这类请求判定为 general_guidance，不能让用户再选已经明确问过的问题。
用户未指定时间时，不添加 week_range；评论数与提及数分开说明。
不要自行补充年份、周次或情绪过滤；用户未限定情绪时应覆盖正面、负面与中性反馈。
问题指定单个产品时，每次统计和检索都必须限定该产品的 sku_codes，不能查询全库后混用其他产品的证据。
“某产品用户怎么评价”本身已经是明确请求：先查询并总结优缺点；不应要求用户先选一个方面才查询。
可以组合工具，不设固定调用顺序。只有用户明确要求读取已有周报时才使用 tool_report。
周报 not_found 后应重新评估：指标用 tool_sql、例子用 tool_rag，不能仅因没有周报就放弃查询。
参数用JSON对象，sku_codes是数组；week_range为
{"start_week_id": YYYYWW, "end_week_id": YYYYWW}。遵守工具给出的容量档位限制。

最终输出协议（不展示给用户）：
返回JSON对象，仅有 answer（面向用户的完整回答字符串）、cited_evidence_ids（实际引用的
aspect_mentions UUID数组，无引用时为空）、answer_kind 三个字段。
answer_kind 只能是 general_guidance 或 data_answer。根据当前请求判定，而不是根据回答语气判定。
answer内容由当前问题决定，没有任何固定台词。引用必须匹配实际检索到的证据。
Return exactly one JSON object with keys "answer", "cited_evidence_ids", "answer_kind".
For non-data conversation, answer_kind MUST be "general_guidance", cited_evidence_ids MUST be [].
For dataset requests, answer_kind MUST be "data_answer". Do not omit answer_kind."""

NO_DATA_ANSWER = (
    "The VOC dataset does not provide sufficient evidence for this request. "
    "Try broadening the SKU, week, or evidence filters."
)

ToolExecutor = Callable[[AgentSchema], Awaitable[ToolResult[Any, Any]]]
ToolLifecycleSink = Callable[[ToolStartedEvent | ToolCompletedEvent], Awaitable[None]]


@dataclass(frozen=True)
class ToolBinding:
    name: ToolName
    description: str
    argument_model: type[AgentSchema]
    executor: ToolExecutor

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name.value,
                "description": self.description,
                "parameters": deepcopy(_PROVIDER_TOOL_PARAMETERS[self.name]),
            },
        }


def build_tool_bindings(
    *, report_service: Any, analytics_service: Any, rag_service: Any
) -> list[ToolBinding]:
    """Bind only the three approved Week 3 capabilities."""
    return [
        ToolBinding(
            name=ToolName.REPORT,
            description=(
                "Read an already-generated weekly macro report by SKU and ISO week. "
                "It never generates a report or performs fallback analysis."
            ),
            argument_model=ReportToolArguments,
            executor=report_service.execute,
        ),
        ToolBinding(
            name=ToolName.SQL,
            description=(
                "Run one approved deterministic analytics operation for counts, "
                "distributions, trends, aspect trends, or same-tier SKU comparison."
                " To list available products, call operation=review_count with sku_codes=[]; "
                "the by_sku result contains all currently enabled SKU codes."
            ),
            argument_model=AnalyticsToolArguments,
            executor=analytics_service.execute,
        ),
        ToolBinding(
            name=ToolName.RAG,
            description=(
                "Retrieve traceable qualitative VOC evidence and exact examples using "
                "structured SKU, week, sentiment, aspect, and top-k filters."
            ),
            argument_model=RagToolArguments,
            executor=rag_service.execute,
        ),
    ]


class FunctionCallingRouter:
    def __init__(
        self,
        model: ChatModelProtocol,
        tool_bindings: Sequence[ToolBinding],
        *,
        system_policy: str,
        max_model_rounds: int = MAX_MODEL_ROUNDS,
    ) -> None:
        if max_model_rounds < 2:
            raise ValueError("max_model_rounds must be at least 2")
        bindings = {binding.name.value: binding for binding in tool_bindings}
        if len(bindings) != len(tool_bindings):
            raise ValueError("tool binding names must be unique")
        if set(bindings) - {item.value for item in ToolName}:
            raise ValueError("only approved Week 3 tools may be bound")
        self._model = model
        self._bindings = bindings
        self._system_policy = system_policy.strip()
        self._max_model_rounds = max_model_rounds

    async def run(
        self,
        *,
        recent_messages: Sequence[ConversationMessage],
        current_user_message: str,
        event_sink: ToolLifecycleSink | None = None,
    ) -> AgentRunResult:
        if not current_user_message.strip():
            raise ValueError("current_user_message must not be blank")
        messages = self._initial_messages(recent_messages, current_user_message)
        scope = resolve_scope(current_user_message, recent_messages)
        definitions = [binding.definition() for binding in self._bindings.values()]
        traces: list[ToolCallTrace] = []
        results: list[ToolResult[Any, Any]] = []
        evidence: list[RetrievedEvidence] = []
        warnings: list[ToolWarning] = []
        fingerprints: set[str] = set()
        attempted = 0
        executed = 0
        model_rounds = 0
        limit_event: ToolCallLimitEvent | None = None
        force_final = False
        report_miss_needs_reassessment = False
        report_miss_reprompted = False
        unsupported_final_reprompted = False
        format_correction_attempted = False
        format_correction_pending = False
        format_messages: list[dict[str, Any]] = []

        while model_rounds < self._max_model_rounds:
            try:
                response = await self._model.complete(
                    messages=format_messages if format_correction_pending else messages,
                    tools=[]
                    if force_final or format_correction_pending
                    else definitions,
                )
            except Exception as exc:
                model_rounds += 1
                return self._controlled_error(
                    "The language model is temporarily unavailable.",
                    traces,
                    warnings,
                    model_rounds,
                    attempted,
                    executed,
                    limit_event,
                    error=ToolError(
                        code=(
                            "llm_timeout"
                            if isinstance(exc, TimeoutError)
                            else "llm_request_failed"
                        ),
                        message="The language model is temporarily unavailable.",
                        retryable=True,
                    ),
                )
            model_rounds += 1
            format_correction_pending = False
            if scope.data_request and response.answer_kind == "general_guidance":
                response = replace(response, answer_kind="data_answer")
            if (
                response.requires_formatting
                and not response.tool_calls
                and not format_correction_attempted
                and model_rounds < self._max_model_rounds
            ):
                # Some compatible providers ignore JSON mode while tools are
                # present. Repair once without tools, counting the extra round.
                format_correction_attempted = True
                format_correction_pending = True
                format_messages = [
                    {
                        "role": "system",
                        "content": (
                            "你只负责把草稿转成JSON，不重新回答问题。把draft_answer完整原样放入answer，"
                            "不要缩写、续写或改成欢迎语。根据current_user_message判定answer_kind："
                            "问候、定位、能力介绍、系统用法、通用概念、请求提问示例或澄清，属于"
                            "general_guidance。请求真实产品目录、统计、趋势、产品反馈或客户原文属于"
                            "data_answer，包括这类请求的拒答。用法解释中的产品名称和提问例子不等于"
                            "用户在查询数据，不要根据draft_answer提到的主题误判。只判断当前问题，"
                            "不延续之前的问候。cited_evidence_ids仅包含草稿实际引用的证据ID，"
                            "从available_evidence中选择；没引用时用空数组。"
                            "Return exactly one JSON object with keys answer (string), "
                            "cited_evidence_ids (array of strings), answer_kind "
                            "(general_guidance or data_answer)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "current_user_message": current_user_message,
                                "draft_answer": response.content,
                                "available_evidence": [
                                    {
                                        "id": str(item.mention_id),
                                        "text": item.mention_text,
                                    }
                                    for item in evidence
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
                continue
            if (
                not response.tool_calls
                and not force_final
                and scope.review_count_requested
                and not scope.time_requested
                and not scope.sentiment_requested
                and "tool_sql" in scope.tools
                and "tool_sql" in self._bindings
                and attempted < MAX_TOOL_CALLS
                and not any(r.tool_name is ToolName.SQL for r in results)
            ):
                response = replace(
                    response,
                    tool_calls=[
                        ModelToolCall(
                            call_id=f"recovery-count-{model_rounds}",
                            name="tool_sql",
                            arguments={
                                "operation": "review_count",
                                "sku_codes": list(scope.skus),
                            },
                        )
                    ],
                )
            # A supported qualitative request has an unambiguous recovery:
            # retrieve the user's question within its resolved SKU scope. Keep
            # this inside the ordinary validation, lifecycle and call budget.
            if (
                not response.tool_calls
                and not force_final
                and "tool_rag" in scope.tools
                and "tool_rag" in self._bindings
                and attempted < MAX_TOOL_CALLS
                and not any(r.tool_name is ToolName.RAG for r in results)
            ):
                response = replace(
                    response,
                    tool_calls=[
                        ModelToolCall(
                            call_id=f"recovery-rag-{model_rounds}",
                            name="tool_rag",
                            arguments={
                                "query": current_user_message,
                                "sku_codes": list(scope.skus),
                            },
                        )
                    ],
                )
            if response.tool_calls:
                if force_final:
                    return self._controlled_error(
                        "The model did not produce a final answer after the tool-call limit.",
                        traces,
                        warnings,
                        model_rounds,
                        attempted + len(response.tool_calls),
                        executed,
                        limit_event,
                    )
                messages.append(self._assistant_tool_call_message(response.tool_calls))
                limit_reached_this_round = False
                if any(
                    call.name != ToolName.REPORT.value for call in response.tool_calls
                ):
                    report_miss_needs_reassessment = False
                for call in response.tool_calls:
                    attempted += 1
                    if attempted > MAX_TOOL_CALLS:
                        error = ToolError(
                            code="tool_call_limit_exceeded",
                            message=f"Maximum tool calls per request is {MAX_TOOL_CALLS}.",
                            details={"maximum": MAX_TOOL_CALLS},
                        )
                        if limit_event is None:
                            limit_event = ToolCallLimitEvent(
                                attempted_call_id=call.call_id,
                                attempted_tool_name=call.name,
                                maximum=MAX_TOOL_CALLS,
                            )
                        traces.append(self._failed_trace(call, error))
                        messages.append(self._tool_error_message(call, error))
                        limit_reached_this_round = True
                        continue

                    binding = self._bindings.get(call.name)
                    if binding is None:
                        error = ToolError(
                            code="unapproved_tool",
                            message="The requested tool is not approved.",
                            details={"tool_name": call.name},
                        )
                        traces.append(self._failed_trace(call, error))
                        messages.append(self._tool_error_message(call, error))
                        continue
                    try:
                        normalized_call_arguments = self._normalize_provider_arguments(
                            binding.name, call.arguments
                        )
                        if isinstance(normalized_call_arguments, dict):
                            normalized_call_arguments = constrain_arguments(
                                scope, call.name, normalized_call_arguments
                            )
                        arguments = binding.argument_model.model_validate(
                            normalized_call_arguments
                        )
                    except ValidationError as exc:
                        error = ToolError(
                            code="invalid_tool_arguments",
                            message="Tool arguments failed schema validation.",
                            details={"validation_error_count": exc.error_count()},
                        )
                        traces.append(self._failed_trace(call, error))
                        messages.append(self._tool_error_message(call, error))
                        continue

                    fingerprint = self._fingerprint(call.name, arguments)
                    if fingerprint in fingerprints:
                        error = ToolError(
                            code="duplicate_tool_call",
                            message="An identical tool call was already attempted.",
                        )
                        traces.append(
                            self._failed_trace(
                                call,
                                error,
                                normalized_arguments=arguments.model_dump(mode="json"),
                            )
                        )
                        messages.append(self._tool_error_message(call, error))
                        continue
                    fingerprints.add(fingerprint)
                    executed += 1
                    if event_sink is not None:
                        await event_sink(
                            ToolStartedEvent(
                                call_id=call.call_id,
                                tool_name=binding.name,
                            )
                        )
                    try:
                        result = await binding.executor(arguments)
                        if not isinstance(result, ToolResult):
                            raise TypeError("tool executor did not return ToolResult")
                    except Exception:
                        error = ToolError(
                            code="tool_execution_failed",
                            message=f"{call.name} failed during execution.",
                            retryable=True,
                        )
                        failed_trace = self._failed_trace(
                            call,
                            error,
                            executed=True,
                            normalized_arguments=arguments.model_dump(mode="json"),
                        )
                        traces.append(failed_trace)
                        await self._emit_tool_completed(failed_trace, event_sink)
                        messages.append(self._tool_error_message(call, error))
                        continue

                    results.append(result)
                    warnings.extend(result.warnings)
                    completed_trace = ToolCallTrace(
                        call_id=call.call_id,
                        tool_name=call.name,
                        arguments=call.arguments,
                        normalized_arguments=result.normalized_args.model_dump(
                            mode="json"
                        ),
                        executed=True,
                        status=result.status,
                        duration_ms=result.execution.duration_ms,
                        result_count=result.execution.result_count,
                        warnings=result.warnings,
                        error=result.error,
                    )
                    traces.append(completed_trace)
                    await self._emit_tool_completed(completed_trace, event_sink)
                    messages.append(self._tool_result_message(call, result))
                    evidence.extend(self._retrieved_evidence(result))
                    if (
                        result.tool_name is ToolName.REPORT
                        and result.status is ToolStatus.NOT_FOUND
                    ):
                        report_miss_needs_reassessment = True

                if limit_reached_this_round:
                    if not self._has_material_support(results):
                        return self._controlled_error(
                            "The tool-call limit was reached before sufficient VOC evidence was available.",
                            traces,
                            warnings,
                            model_rounds,
                            attempted,
                            executed,
                            limit_event,
                        )
                    force_final = True
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "The application tool-call limit has been reached. Do not request "
                                "more tools. Synthesize only from available structured results."
                            ),
                        }
                    )
                continue

            if (
                report_miss_needs_reassessment
                and not report_miss_reprompted
                and attempted < MAX_TOOL_CALLS
            ):
                report_miss_reprompted = True
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "The stored report was not found and does not answer the original "
                            "request. Before giving a final answer, reconsider whether the request "
                            "needs tool_sql for metrics and/or tool_rag for traceable examples. "
                            "Choose only approved tools and valid JSON arguments; abstain only if "
                            "those tools cannot provide VOC evidence."
                        ),
                    }
                )
                continue

            if (
                definitions
                and not traces
                and not results
                and not unsupported_final_reprompted
                and not self._is_direct_guidance(response, traces, results)
            ):
                unsupported_final_reprompted = True
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "No approved tool result supports a VOC answer yet. Reassess the "
                            "user request and call tool_sql for metrics and/or tool_rag for "
                            "traceable examples. Do not answer from general knowledge."
                            " If the request only needs capability or usage guidance, a greeting, "
                            "a general VOC definition, or clarification, return structured JSON "
                            "with answer_kind=general_guidance and no dataset claims or citations."
                            " For the available product catalog, call tool_sql with "
                            '{"operation":"review_count","sku_codes":[]}.'
                        ),
                    }
                )
                continue

            if not response.content or not response.content.strip():
                return self._controlled_error(
                    "The model returned neither a tool call nor a final answer.",
                    traces,
                    warnings,
                    model_rounds,
                    attempted,
                    executed,
                    limit_event,
                )
            completed_tools = {
                r.tool_name.value
                for r in results
                if r.status
                in {
                    ToolStatus.SUCCESS,
                    ToolStatus.PARTIAL,
                    ToolStatus.EMPTY,
                    ToolStatus.NOT_FOUND,
                }
                or (
                    r.error is not None
                    and r.error.code
                    in {"capacity_tier_mismatch", "capacity_tier_unavailable"}
                )
            }
            missing = scope.tools - completed_tools
            if (
                missing
                and attempted < MAX_TOOL_CALLS
                and model_rounds < self._max_model_rounds
            ):
                messages.append(
                    {
                        "role": "system",
                        "content": "The request still has unanswered intents. Call these tools before finalizing: "
                        + ", ".join(sorted(missing)),
                    }
                )
                continue
            if missing:
                warnings.append(
                    ToolWarning(
                        code="incomplete_request",
                        message="部分问题尚未取得查询结果，无法对这些部分作出结论。",
                    )
                )
            if self._requires_citation_correction(response, results, evidence) or (
                "tool_rag" in scope.tools
                and evidence
                and not response.cited_evidence_ids
            ):
                if model_rounds >= self._max_model_rounds:
                    return self._finalize(
                        response,
                        traces=traces,
                        results=results,
                        evidence=evidence,
                        warnings=warnings,
                        model_rounds=model_rounds,
                        attempted=attempted,
                        executed=executed,
                        limit_event=limit_event,
                    )
                messages.append({"role": "assistant", "content": response.content})
                messages.append(self._citation_correction_message(evidence))
                try:
                    response = await self._model.complete(messages=messages, tools=[])
                except Exception as exc:
                    model_rounds += 1
                    return self._controlled_error(
                        "The language model is temporarily unavailable.",
                        traces,
                        warnings,
                        model_rounds,
                        attempted,
                        executed,
                        limit_event,
                        error=ToolError(
                            code=(
                                "llm_timeout"
                                if isinstance(exc, TimeoutError)
                                else "llm_request_failed"
                            ),
                            message="The language model is temporarily unavailable.",
                            retryable=True,
                        ),
                    )
                model_rounds += 1
                if (
                    response.tool_calls
                    or not response.content
                    or not response.content.strip()
                ):
                    return self._controlled_error(
                        "The citation correction did not return a final JSON answer.",
                        traces,
                        warnings,
                        model_rounds,
                        attempted,
                        executed,
                        limit_event,
                    )
            if (
                "tool_rag" in scope.tools
                and evidence
                and not response.cited_evidence_ids
            ):
                return self._controlled_error(
                    "反馈检索已完成，但回答未能提供可核验的引用，请重试。",
                    traces,
                    warnings,
                    model_rounds,
                    attempted,
                    executed,
                    limit_event,
                )
            return self._finalize(
                response,
                traces=traces,
                results=results,
                evidence=evidence,
                warnings=warnings,
                model_rounds=model_rounds,
                attempted=attempted,
                executed=executed,
                limit_event=limit_event,
            )

        return self._controlled_error(
            "The router stopped after too many model rounds.",
            traces,
            warnings,
            model_rounds,
            attempted,
            executed,
            limit_event,
        )

    @staticmethod
    async def _emit_tool_completed(
        trace: ToolCallTrace,
        event_sink: ToolLifecycleSink | None,
    ) -> None:
        if event_sink is None:
            return
        await event_sink(
            ToolCompletedEvent(
                call_id=trace.call_id,
                tool_name=ToolName(trace.tool_name),
                status=trace.status,
                warnings=trace.warnings,
                execution=ToolExecutionMetadata(
                    duration_ms=trace.duration_ms,
                    result_count=trace.result_count,
                    call_id=trace.call_id,
                ),
            )
        )

    def _initial_messages(
        self,
        recent_messages: Sequence[ConversationMessage],
        current_user_message: str,
    ) -> list[dict[str, Any]]:
        policy = (
            f"{self._system_policy}\n\n{VOC_SYSTEM_POLICY}"
            if self._system_policy and self._system_policy != VOC_SYSTEM_POLICY
            else VOC_SYSTEM_POLICY
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": policy}]
        messages.extend(message.model_dump(mode="json") for message in recent_messages)
        messages.append({"role": "user", "content": current_user_message.strip()})
        return messages

    @staticmethod
    def _requires_citation_correction(
        response: ModelResponse,
        results: Sequence[ToolResult[Any, Any]],
        evidence: Sequence[RetrievedEvidence],
    ) -> bool:
        if not response.content or not evidence:
            return False
        if not any(
            result.tool_name is ToolName.RAG
            and result.status in {ToolStatus.SUCCESS, ToolStatus.PARTIAL}
            and result.payload is not None
            for result in results
        ):
            return False
        if not any(item.mention_text in response.content for item in evidence):
            return False
        retrieved_ids = {str(item.mention_id) for item in evidence}
        return not response.cited_evidence_ids or not set(
            response.cited_evidence_ids
        ).issubset(retrieved_ids)

    @staticmethod
    def _citation_correction_message(
        evidence: Sequence[RetrievedEvidence],
    ) -> dict[str, str]:
        allowed_ids = [str(item.mention_id) for item in evidence]
        return {
            "role": "system",
            "content": (
                "Your previous answer used an exact retrieved VOC example without a valid "
                "citation. Return exactly one JSON object and no markdown: "
                '{"answer":"user-facing grounded answer","cited_evidence_ids":["UUID"]}. '
                "Preserve only claims supported by the available tool results. If the answer "
                "uses an exact retrieved example, cite only its matching ID from this allowed "
                f"list: {allowed_ids}. If the answer uses no retrieved evidence, return an empty "
                "cited_evidence_ids list."
            ),
        }

    @staticmethod
    def _normalize_provider_arguments(
        tool_name: ToolName,
        raw_arguments: dict[str, Any] | str,
    ) -> dict[str, Any] | str:
        """Normalize safe provider naming variants before strict Pydantic validation."""
        if not isinstance(raw_arguments, dict):
            return raw_arguments
        arguments = dict(raw_arguments)
        for wrapper in ("arguments", "parameters"):
            wrapped = arguments.get(wrapper)
            if len(arguments) == 1 and isinstance(wrapped, dict):
                arguments = dict(wrapped)

        if tool_name is ToolName.REPORT:
            return arguments

        def move(source: str, target: str) -> None:
            if target not in arguments and source in arguments:
                arguments[target] = arguments.pop(source)

        move("sku_code", "sku_codes")
        move("sku", "sku_codes")
        if isinstance(arguments.get("sku_codes"), str):
            arguments["sku_codes"] = [arguments["sku_codes"]]

        if "week_range" not in arguments:
            week_id = arguments.pop("week_id", arguments.pop("week", None))
            if isinstance(week_id, int):
                arguments["week_range"] = {
                    "start_week_id": week_id,
                    "end_week_id": week_id,
                }
            elif "start_week_id" in arguments or "end_week_id" in arguments:
                arguments["week_range"] = {
                    "start_week_id": arguments.pop("start_week_id", None),
                    "end_week_id": arguments.pop("end_week_id", None),
                }

        if tool_name is ToolName.SQL:
            move("aspect", "aspect_label")
            move("metric", "comparison_metric")
        elif tool_name is ToolName.RAG:
            move("search_query", "query")
            move("semantic_query", "query")
            move("aspect", "aspect_label")
            move("limit", "top_k")
        return arguments

    @staticmethod
    def _assistant_tool_call_message(
        tool_calls: Sequence[ModelToolCall],
    ) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": (
                            json.dumps(call.arguments, sort_keys=True)
                            if isinstance(call.arguments, dict)
                            else call.arguments
                        ),
                    },
                }
                for call in tool_calls
            ],
        }

    @staticmethod
    def _tool_result_message(
        call: ModelToolCall, result: ToolResult[Any, Any]
    ) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        if result.tool_name is ToolName.RAG and payload.get("payload"):
            for item in payload["payload"].get("evidence", []):
                item.get("source", {}).pop("review_text", None)
        return {
            "role": "tool",
            "tool_call_id": call.call_id,
            "name": call.name,
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        }

    @staticmethod
    def _tool_error_message(call: ModelToolCall, error: ToolError) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.call_id,
            "name": call.name,
            "content": json.dumps(
                {"status": "error", "error": error.model_dump(mode="json")},
                ensure_ascii=False,
                sort_keys=True,
            ),
        }

    @staticmethod
    def _fingerprint(tool_name: str, arguments: AgentSchema) -> str:
        return f"{tool_name}:{arguments.model_dump_json(exclude_none=False)}"

    @staticmethod
    def _failed_trace(
        call: ModelToolCall,
        error: ToolError,
        *,
        executed: bool = False,
        normalized_arguments: dict[str, Any] | None = None,
    ) -> ToolCallTrace:
        return ToolCallTrace(
            call_id=call.call_id,
            tool_name=call.name,
            arguments=call.arguments,
            normalized_arguments=normalized_arguments,
            executed=executed,
            status=ToolStatus.ERROR,
            error=error,
        )

    @staticmethod
    def _retrieved_evidence(
        result: ToolResult[Any, Any],
    ) -> list[RetrievedEvidence]:
        if result.tool_name is not ToolName.RAG or result.payload is None:
            return []
        payload_evidence = getattr(result.payload, "evidence", None)
        return list(payload_evidence) if payload_evidence is not None else []

    @staticmethod
    def _is_direct_guidance(
        response: ModelResponse,
        traces: Sequence[ToolCallTrace],
        results: Sequence[ToolResult[Any, Any]],
    ) -> bool:
        # Fail closed for legacy/unstructured responses, citations, or attempted
        # data queries. Failed queries must still follow the grounding path.
        return (
            response.answer_kind == "general_guidance"
            and not traces
            and not results
            and not response.cited_evidence_ids
        )

    @staticmethod
    def _has_material_support(results: Sequence[ToolResult[Any, Any]]) -> bool:
        for result in results:
            if (
                result.status in {ToolStatus.SUCCESS, ToolStatus.PARTIAL}
                and result.payload is not None
            ):
                return True
            if result.error and result.error.code in {
                "capacity_tier_mismatch",
                "capacity_tier_unavailable",
            }:
                return True
        return False

    def _finalize(
        self,
        response: ModelResponse,
        *,
        traces: list[ToolCallTrace],
        results: list[ToolResult[Any, Any]],
        evidence: list[RetrievedEvidence],
        warnings: list[ToolWarning],
        model_rounds: int,
        attempted: int,
        executed: int,
        limit_event: ToolCallLimitEvent | None,
    ) -> AgentRunResult:
        execution = self._execution(model_rounds, attempted, executed, limit_event)
        if results and all(
            result.status in {ToolStatus.EMPTY, ToolStatus.NOT_FOUND}
            for result in results
        ):
            return AgentRunResult(
                status=AgentStatus.ABSTAINED,
                final_answer=NO_DATA_ANSWER,
                warnings=warnings,
                tool_trace=traces,
                execution=execution,
            )

        support = self._has_material_support(results)
        constraint_only = any(
            result.error
            and result.error.code
            in {"capacity_tier_mismatch", "capacity_tier_unavailable"}
            for result in results
        )
        if (
            not support
            and not constraint_only
            and not self._is_direct_guidance(response, traces, results)
        ):
            return self._controlled_error(
                "No successful tool result supports a VOC answer.",
                traces,
                warnings,
                model_rounds,
                attempted,
                executed,
                limit_event,
            )

        try:
            cited_ids = [UUID(item) for item in response.cited_evidence_ids]
            citations = build_answer_citations(evidence, cited_ids)
        except (ValueError, TypeError):
            return self._controlled_error(
                "The final answer referenced an invalid or unretrieved evidence ID.",
                traces,
                warnings,
                model_rounds,
                attempted,
                executed,
                limit_event,
            )
        cited_set = {item.mention_id for item in citations}
        if any(
            item.mention_text in response.content and item.mention_id not in cited_set
            for item in evidence
        ):
            return self._controlled_error(
                "The final answer used exact retrieved evidence without citing its ID.",
                traces,
                warnings,
                model_rounds,
                attempted,
                executed,
                limit_event,
            )

        answer = self._append_data_notes(response.content.strip(), traces, warnings)
        operational_errors = [
            trace
            for trace in traces
            if trace.status is ToolStatus.ERROR
            and trace.error is not None
            and trace.error.code
            not in {
                "capacity_tier_mismatch",
                "capacity_tier_unavailable",
                "duplicate_tool_call",
            }
        ]
        partial = (
            limit_event is not None
            or bool(operational_errors)
            or any(w.code == "incomplete_request" for w in warnings)
            or any(result.status is ToolStatus.PARTIAL for result in results)
        )
        return AgentRunResult(
            status=AgentStatus.PARTIAL if partial else AgentStatus.SUCCESS,
            final_answer=answer,
            citations=citations,
            warnings=warnings,
            tool_trace=traces,
            execution=execution,
        )

    @staticmethod
    def _append_data_notes(
        answer: str,
        traces: Sequence[ToolCallTrace],
        warnings: Sequence[ToolWarning],
    ) -> str:
        notes = [warning.message for warning in warnings]
        notes.extend(
            trace.error.message
            for trace in traces
            if trace.error is not None
            and trace.error.code
            not in {"duplicate_tool_call", "tool_call_limit_exceeded"}
        )
        unique_notes = list(dict.fromkeys(notes))
        if not unique_notes:
            return answer
        rendered = "\n".join(f"- {note}" for note in unique_notes)
        return f"{answer}\n\nData notes:\n{rendered}"

    @staticmethod
    def _execution(
        model_rounds: int,
        attempted: int,
        executed: int,
        limit_event: ToolCallLimitEvent | None,
    ) -> AgentExecutionMetadata:
        return AgentExecutionMetadata(
            model_round_count=model_rounds,
            attempted_tool_call_count=attempted,
            executed_tool_call_count=executed,
            maximum_tool_calls=MAX_TOOL_CALLS,
            limit_event=limit_event,
        )

    def _controlled_error(
        self,
        answer: str,
        traces: list[ToolCallTrace],
        warnings: list[ToolWarning],
        model_rounds: int,
        attempted: int,
        executed: int,
        limit_event: ToolCallLimitEvent | None,
        error: ToolError | None = None,
    ) -> AgentRunResult:
        return AgentRunResult(
            status=AgentStatus.ERROR,
            final_answer=answer,
            error=error
            or ToolError(code="agent_request_failed", message=answer, retryable=True),
            warnings=warnings,
            tool_trace=traces,
            execution=self._execution(model_rounds, attempted, executed, limit_event),
        )
