import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.agent.conversation import ConversationService, UnknownSessionError
from backend.app.agent.llm import ModelResponse, ModelToolCall
from backend.app.agent.router import FunctionCallingRouter, ToolBinding
from backend.app.agent.schemas import (
    AgentExecutionMetadata,
    AgentRunResult,
    AgentSchema,
    AgentStatus,
    AnalyticsToolArguments,
    AnswerCitation,
    ConversationMessage,
    ExpandedSourceMetadata,
    RagRetrievalPayload,
    RagToolArguments,
    RagToolResult,
    RetrievedEvidence,
    ToolCallTrace,
    ToolError,
    ToolExecutionMetadata,
    ToolName,
    ToolResult,
    ToolStatus,
)
from backend.app.core.settings import Settings
from backend.app.db.repositories.conversation_repo import ConversationRepository
from backend.app.db.repositories.schemas import (
    ChatMessageRead,
    ChatSessionRead,
    PersistedTurnRow,
)

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, ChatSessionRead] = {}
        self.messages: dict[UUID, list[ChatMessageRead]] = {}
        self.requested_limits: list[int] = []
        self.persisted_metadata: list[dict[str, Any]] = []
        self.fail_persist = False

    async def create_session(
        self, *, title: str | None = None, created_by: str | None = None
    ) -> ChatSessionRead:
        session = ChatSessionRead(
            id=uuid4(),
            title=title,
            created_by=created_by,
            is_active=True,
            created_at=NOW,
            updated_at=NOW,
        )
        self.sessions[session.id] = session
        self.messages[session.id] = []
        return session

    async def get_session(self, session_id: UUID) -> ChatSessionRead | None:
        return self.sessions.get(session_id)

    async def get_recent_messages(
        self, session_id: UUID, *, limit: int
    ) -> list[ChatMessageRead]:
        self.requested_limits.append(limit)
        return list(self.messages[session_id][-limit:])

    async def persist_turn(self, **kwargs) -> PersistedTurnRow:
        if self.fail_persist:
            raise RuntimeError("database write failed")
        session_id = kwargs["session_id"]
        existing = self.messages[session_id]
        user_id = uuid4()
        assistant_id = uuid4()
        sequence = len(existing)
        user = ChatMessageRead(
            id=user_id,
            session_id=session_id,
            role="user",
            content=kwargs["user_content"],
            tool_calls=None,
            tool_results=None,
            cited_ids=None,
            created_at=NOW + timedelta(microseconds=sequence),
        )
        assistant = ChatMessageRead(
            id=assistant_id,
            session_id=session_id,
            role="assistant",
            content=kwargs["assistant_content"],
            tool_calls=kwargs["tool_calls"],
            tool_results=kwargs["tool_results"],
            cited_ids=kwargs["cited_ids"],
            created_at=NOW + timedelta(microseconds=sequence + 1),
        )
        existing.extend([user, assistant])
        self.persisted_metadata.append(kwargs)
        return PersistedTurnRow(
            user_message_id=user_id, assistant_message_id=assistant_id
        )

    def seed_message(self, session_id: UUID, role: str, content: str) -> None:
        sequence = len(self.messages[session_id])
        self.messages[session_id].append(
            ChatMessageRead(
                id=uuid4(),
                session_id=session_id,
                role=role,
                content=content,
                tool_calls=None,
                tool_results=None,
                cited_ids=None,
                created_at=NOW + timedelta(microseconds=sequence),
            )
        )


class RecordingRouter:
    def __init__(self, results: list[AgentRunResult]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def run(
        self,
        *,
        recent_messages: list[ConversationMessage],
        current_user_message: str,
    ) -> AgentRunResult:
        self.calls.append(
            {
                "recent_messages": recent_messages,
                "current_user_message": current_user_message,
            }
        )
        return self.results.pop(0)


def agent_result(
    answer: str = "Supported answer.",
    *,
    status: AgentStatus = AgentStatus.SUCCESS,
    trace: list[ToolCallTrace] | None = None,
    citations: list[AnswerCitation] | None = None,
    error: ToolError | None = None,
) -> AgentRunResult:
    return AgentRunResult(
        status=status,
        final_answer=answer,
        error=error,
        citations=citations or [],
        tool_trace=trace or [],
        execution=AgentExecutionMetadata(
            model_round_count=2,
            attempted_tool_call_count=len(trace or []),
            executed_tool_call_count=sum(item.executed for item in (trace or [])),
            maximum_tool_calls=3,
        ),
    )


@pytest.mark.asyncio
async def test_create_session_uses_existing_session_contract() -> None:
    repository = InMemoryConversationRepository()
    service = ConversationService(repository, RecordingRouter([]))

    session = await service.create_session(title="  Delta comparison  ")

    assert session.title == "Delta comparison"
    assert session.is_active is True
    assert repository.messages[session.id] == []
    assert Settings.model_fields["recent_message_limit"].default == 8


@pytest.mark.asyncio
async def test_reuse_session_loads_visible_previous_turn() -> None:
    repository = InMemoryConversationRepository()
    router = RecordingRouter(
        [agent_result("First answer."), agent_result("Second answer.")]
    )
    service = ConversationService(repository, router)
    session = await service.create_session()

    await service.run_turn(session_id=session.id, user_message="First question")
    second = await service.run_turn(
        session_id=str(session.id), user_message="Follow-up"
    )

    assert second.session_id == session.id
    assert [item.model_dump() for item in router.calls[1]["recent_messages"]] == [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "First answer."},
    ]
    assert len(repository.messages[session.id]) == 4


@pytest.mark.asyncio
async def test_only_configured_recent_n_messages_are_loaded_in_order() -> None:
    repository = InMemoryConversationRepository()
    router = RecordingRouter([agent_result()])
    service = ConversationService(repository, router, recent_message_limit=3)
    session = await service.create_session()
    for index in range(6):
        repository.seed_message(
            session.id,
            "user" if index % 2 == 0 else "assistant",
            f"message-{index}",
        )

    await service.run_turn(session_id=session.id, user_message="current")

    assert repository.requested_limits == [3]
    assert [item.content for item in router.calls[0]["recent_messages"]] == [
        "message-3",
        "message-4",
        "message-5",
    ]


@pytest.mark.asyncio
async def test_compact_tool_metadata_excludes_raw_payloads() -> None:
    mention_id = uuid4()
    document_id = uuid4()
    citation = AnswerCitation(
        mention_id=mention_id,
        document_id=document_id,
        evidence_preview="fan is loud",
        sku_code="ecoflow-delta2",
        aspect_label="noise_level",
        sentiment="negative",
        week_id=202635,
        source=ExpandedSourceMetadata(
            document_id=document_id,
            sku_code="ecoflow-delta2",
            platform="amazon",
            review_text="FULL REVIEW MUST NOT BE PERSISTED",
        ),
    )
    trace = ToolCallTrace(
        call_id="rag-1",
        tool_name="tool_rag",
        arguments={
            "query": "noise",
            "review_text": "FULL REVIEW MUST NOT BE PERSISTED",
            "embedding": [0.1, 0.2],
            "payload": {"large": "raw result"},
        },
        normalized_arguments={
            "query": "noise",
            "sku_codes": ["ecoflow-delta2"],
            "top_k": 3,
        },
        executed=True,
        status=ToolStatus.SUCCESS,
        duration_ms=12,
        result_count=3,
    )
    repository = InMemoryConversationRepository()
    service = ConversationService(
        repository,
        RecordingRouter([agent_result(trace=[trace], citations=[citation])]),
    )
    session = await service.create_session()

    await service.run_turn(session_id=session.id, user_message="Show comments")

    metadata = repository.persisted_metadata[0]
    serialized = json.dumps(
        {
            "tool_calls": metadata["tool_calls"],
            "tool_results": metadata["tool_results"],
        }
    )
    assert metadata["tool_calls"]["calls"][0]["normalized_arguments"] == {
        "query": "noise",
        "sku_codes": ["ecoflow-delta2"],
        "top_k": 3,
    }
    assert metadata["tool_results"]["results"][0] == {
        "call_id": "rag-1",
        "tool_name": "tool_rag",
        "status": "success",
        "result_count": 3,
        "duration_ms": 12,
        "warnings": [],
        "error": None,
    }
    assert metadata["cited_ids"] == {"mention_ids": [str(mention_id)]}
    assert "FULL REVIEW" not in serialized
    assert "embedding" not in serialized
    assert '"payload"' not in serialized


@pytest.mark.asyncio
async def test_malformed_and_unknown_session_are_rejected_before_router() -> None:
    repository = InMemoryConversationRepository()
    router = RecordingRouter([])
    service = ConversationService(repository, router)

    with pytest.raises(ValueError, match="valid UUID"):
        await service.run_turn(session_id="not-a-uuid", user_message="question")
    with pytest.raises(UnknownSessionError):
        await service.run_turn(session_id=uuid4(), user_message="question")
    assert router.calls == []


@pytest.mark.asyncio
async def test_tool_failure_is_persisted_consistently_without_success_claim() -> None:
    error = ToolError(
        code="analytics_query_failed",
        message="Analytics data is temporarily unavailable.",
        retryable=True,
    )
    trace = ToolCallTrace(
        call_id="sql-1",
        tool_name="tool_sql",
        arguments={"operation": "review_count"},
        normalized_arguments={"operation": "review_count", "sku_codes": []},
        executed=True,
        status=ToolStatus.ERROR,
        duration_ms=4,
        error=error,
    )
    repository = InMemoryConversationRepository()
    service = ConversationService(
        repository,
        RecordingRouter(
            [
                agent_result(
                    "No successful tool result supports a VOC answer.",
                    status=AgentStatus.ERROR,
                    trace=[trace],
                    error=ToolError(
                        code="llm_timeout",
                        message="The language model is temporarily unavailable.",
                        retryable=True,
                    ),
                )
            ]
        ),
    )
    session = await service.create_session()

    result = await service.run_turn(session_id=session.id, user_message="Count reviews")

    assistant = repository.messages[session.id][-1]
    assert result.agent_result.status is AgentStatus.ERROR
    assert assistant.content == result.agent_result.final_answer
    assert assistant.tool_results["agent_status"] == "error"
    assert assistant.tool_results["agent_error"] == {
        "code": "llm_timeout",
        "retryable": True,
    }
    assert assistant.tool_results["results"][0]["error"] == {
        "code": "analytics_query_failed",
        "retryable": True,
    }


@pytest.mark.asyncio
async def test_persistence_failure_does_not_leave_half_a_turn() -> None:
    repository = InMemoryConversationRepository()
    service = ConversationService(repository, RecordingRouter([agent_result()]))
    session = await service.create_session()
    repository.fail_persist = True

    with pytest.raises(RuntimeError, match="database write failed"):
        await service.run_turn(session_id=session.id, user_message="question")

    assert repository.messages[session.id] == []
    assert repository.persisted_metadata == []


class AcceptanceModel:
    def __init__(self) -> None:
        self.initial_turn_messages: list[list[dict[str, Any]]] = []

    async def complete(self, *, messages, tools) -> ModelResponse:
        current_user = next(
            item["content"] for item in reversed(messages) if item["role"] == "user"
        )
        if messages[-1]["role"] == "tool":
            payload = json.loads(messages[-1]["content"])
            if messages[-1]["name"] == "tool_rag":
                evidence = payload["payload"]["evidence"][0]
                return ModelResponse(
                    content=f'One comment says "{evidence["mention_text"]}."',
                    cited_evidence_ids=[evidence["mention_id"]],
                )
            return ModelResponse(content=f"Supported analysis for: {current_user}")

        self.initial_turn_messages.append(list(messages))
        if current_user == "Compare Delta 2 and Jackery Explorer 1000.":
            return ModelResponse(
                tool_calls=[
                    ModelToolCall(
                        call_id="sql-compare",
                        name="tool_sql",
                        arguments={
                            "operation": "compare_skus",
                            "sku_codes": [
                                "ecoflow-delta2",
                                "jackery-explorer-1000",
                            ],
                        },
                    )
                ]
            )
        if current_user == "What about noise specifically?":
            assert any("Delta 2 and Jackery" in item["content"] for item in messages)
            return ModelResponse(
                tool_calls=[
                    ModelToolCall(
                        call_id="sql-noise",
                        name="tool_sql",
                        arguments={
                            "operation": "compare_skus",
                            "sku_codes": [
                                "ecoflow-delta2",
                                "jackery-explorer-1000",
                            ],
                            "aspect_label": "noise_level",
                        },
                    )
                ]
            )
        assert current_user == "Show me some actual comments."
        assert any(
            "What about noise specifically?" in item["content"] for item in messages
        )
        assert any("Delta 2 and Jackery" in item["content"] for item in messages)
        return ModelResponse(
            tool_calls=[
                ModelToolCall(
                    call_id="rag-comments",
                    name="tool_rag",
                    arguments={
                        "query": "actual noise comments",
                        "sku_codes": [
                            "ecoflow-delta2",
                            "jackery-explorer-1000",
                        ],
                        "aspect_label": "noise_level",
                        "top_k": 8,
                    },
                )
            ]
        )


class AcceptanceSqlExecutor:
    def __init__(self) -> None:
        self.calls: list[AnalyticsToolArguments] = []

    async def __call__(self, arguments: AgentSchema) -> ToolResult[Any, Any]:
        assert isinstance(arguments, AnalyticsToolArguments)
        self.calls.append(arguments)
        return ToolResult[AnalyticsToolArguments, dict[str, int]](
            status=ToolStatus.SUCCESS,
            tool_name=ToolName.SQL,
            normalized_args=arguments,
            execution=ToolExecutionMetadata(duration_ms=3, result_count=2),
            payload={"sku_count": 2},
        )


class AcceptanceRagExecutor:
    def __init__(self) -> None:
        self.calls: list[RagToolArguments] = []
        self.evidence = self._evidence()

    @staticmethod
    def _evidence() -> RetrievedEvidence:
        document_id = uuid4()
        return RetrievedEvidence(
            mention_id=uuid4(),
            document_id=document_id,
            sku_code="ecoflow-delta2",
            aspect_label="noise_level",
            sentiment="negative",
            week_id=202635,
            mention_text="the fan is very loud",
            context_window="At high load, the fan is very loud in a small room.",
            quality_score=0.8,
            similarity_score=0.9,
            source=ExpandedSourceMetadata(
                document_id=document_id,
                sku_code="ecoflow-delta2",
                platform="amazon",
                review_text="At high load, the fan is very loud in a small room.",
            ),
        )

    async def __call__(self, arguments: AgentSchema) -> RagToolResult:
        assert isinstance(arguments, RagToolArguments)
        self.calls.append(arguments)
        return RagToolResult(
            status=ToolStatus.SUCCESS,
            tool_name=ToolName.RAG,
            normalized_args=arguments,
            execution=ToolExecutionMetadata(duration_ms=5, result_count=1),
            payload=RagRetrievalPayload(
                query=arguments.query,
                retrieved_count=1,
                evidence=[self.evidence],
            ),
        )


@pytest.mark.asyncio
async def test_three_turn_acceptance_uses_visible_history_not_hidden_filters() -> None:
    repository = InMemoryConversationRepository()
    model = AcceptanceModel()
    sql_executor = AcceptanceSqlExecutor()
    rag_executor = AcceptanceRagExecutor()
    router = FunctionCallingRouter(
        model,
        [
            ToolBinding(
                name=ToolName.SQL,
                description="analytics",
                argument_model=AnalyticsToolArguments,
                executor=sql_executor,
            ),
            ToolBinding(
                name=ToolName.RAG,
                description="evidence",
                argument_model=RagToolArguments,
                executor=rag_executor,
            ),
        ],
        system_policy="Answer from visible VOC history.",
    )
    service = ConversationService(repository, router, recent_message_limit=8)
    session = await service.create_session(title="Acceptance conversation")

    turn1 = await service.run_turn(
        session_id=session.id,
        user_message="Compare Delta 2 and Jackery Explorer 1000.",
    )
    turn2 = await service.run_turn(
        session_id=session.id,
        user_message="What about noise specifically?",
    )
    turn3 = await service.run_turn(
        session_id=session.id,
        user_message="Show me some actual comments.",
    )

    expected_skus = ["ecoflow-delta2", "jackery-explorer-1000"]
    assert turn1.agent_result.status is AgentStatus.SUCCESS
    assert turn2.agent_result.status is AgentStatus.SUCCESS
    assert turn3.agent_result.status is AgentStatus.SUCCESS
    assert sql_executor.calls[0].sku_codes == expected_skus
    assert sql_executor.calls[1].sku_codes == expected_skus
    assert sql_executor.calls[1].aspect_label == "noise_level"
    assert rag_executor.calls[0].sku_codes == expected_skus
    assert rag_executor.calls[0].aspect_label == "noise_level"
    assert [len(call) - 2 for call in model.initial_turn_messages] == [0, 2, 4]
    assert len(repository.messages[session.id]) == 6
    assert repository.messages[session.id][-1].cited_ids == {
        "mention_ids": [str(rag_executor.evidence.mention_id)]
    }


class EmptyScalarResult:
    def scalars(self):
        return []


class CapturingReadSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return EmptyScalarResult()


@pytest.mark.asyncio
async def test_repository_recent_query_is_bounded_and_newest_first_in_sql() -> None:
    session = CapturingReadSession()
    session_id = uuid4()

    messages = await ConversationRepository(session).get_recent_messages(
        session_id, limit=8
    )

    assert messages == []
    sql = str(session.statement)
    assert "ORDER BY chat_messages.created_at DESC" in sql
    assert "chat_messages.id DESC" in sql
    parameters = session.statement.compile().params.values()
    assert session_id in parameters
    assert 8 in parameters


class NestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class LockedSessionResult:
    def __init__(self) -> None:
        self.chat_session = type(
            "LockedSession", (), {"updated_at": NOW.replace(tzinfo=None)}
        )()

    def scalar_one_or_none(self):
        return self.chat_session


class CapturingWriteSession:
    def __init__(self) -> None:
        self.added = []
        self.statement = None
        self.locked_result = LockedSessionResult()

    def begin_nested(self):
        return NestedTransaction()

    def add_all(self, items) -> None:
        self.added.extend(items)

    async def execute(self, statement):
        self.statement = statement
        return self.locked_result

    async def flush(self) -> None:
        for item in self.added:
            if item.id is None:
                item.id = uuid4()


@pytest.mark.asyncio
async def test_repository_persists_user_before_assistant_deterministically() -> None:
    session = CapturingWriteSession()

    await ConversationRepository(session).persist_turn(
        session_id=uuid4(),
        user_content="question",
        assistant_content="answer",
        tool_calls={"version": 1, "calls": []},
        tool_results={"version": 1, "results": []},
        cited_ids={"mention_ids": []},
    )

    assert [item.role for item in session.added] == ["user", "assistant"]
    assert session.added[0].created_at < session.added[1].created_at
    assert session.locked_result.chat_session.updated_at == session.added[1].created_at
    assert "FOR UPDATE" in str(session.statement)
