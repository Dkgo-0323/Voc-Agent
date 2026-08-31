"""Pure handwritten multi-tool function-calling loop for the VOC Agent."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from backend.app.agent.llm import ChatModelProtocol, ModelResponse, ModelToolCall
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

MAX_TOOL_CALLS = 3
MAX_MODEL_ROUNDS = 8

VOC_SYSTEM_POLICY = """You are the VOC analytical interface for the configured dataset.
Use only approved tools and visible conversation messages. Never fill missing VOC data with
general product knowledge. tool_report only reads stored weekly macro reports. tool_sql is the
only source for deterministic counts, proportions, distributions, trends, and comparisons.
tool_rag is the source for qualitative evidence and exact customer examples. Quantitative claims
must be grounded in tool_sql or an existing stored report; never infer database metrics from RAG
examples. Quotes and examples must come from retrieved evidence or traceable stored report text;
never invent quotes. Keep product comparisons neutral and respect capacity-tier constraints,
sample-size warnings, unavailable metrics, empty results, and tool failures. A partial answer is
allowed only when remaining successful results materially support it, and the unavailable part
must be disclosed. When evidence is insufficient, abstain. You may combine tools; do not force a
single-tool priority chain. Do not reveal chain-of-thought or private planning.

When no more tools are needed, return a JSON object with exactly these fields:
{"answer": "user-facing answer", "cited_evidence_ids": ["aspect_mentions UUIDs actually used"]}
Use an empty cited_evidence_ids list when no retrieved evidence is used."""

NO_DATA_ANSWER = (
    "The VOC dataset does not provide sufficient evidence for this request. "
    "Try broadening the SKU, week, or evidence filters."
)

ToolExecutor = Callable[[AgentSchema], Awaitable[ToolResult[Any, Any]]]
ToolLifecycleSink = Callable[
    [ToolStartedEvent | ToolCompletedEvent], Awaitable[None]
]


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
                "parameters": self.argument_model.model_json_schema(),
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

        while model_rounds < self._max_model_rounds:
            try:
                response = await self._model.complete(
                    messages=messages,
                    tools=[] if force_final else definitions,
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
                        arguments = binding.argument_model.model_validate(
                            call.arguments
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
            if self._system_policy
            else VOC_SYSTEM_POLICY
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": policy}]
        messages.extend(message.model_dump(mode="json") for message in recent_messages)
        messages.append({"role": "user", "content": current_user_message.strip()})
        return messages

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
        if not support and not constraint_only:
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
