import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.agent.conversation import UnknownSessionError
from backend.app.agent.schemas import (
    AgentExecutionMetadata,
    AgentRunResult,
    AgentStatus,
    AnswerCitation,
    ConversationTurnResult,
    ExpandedSourceMetadata,
    Sentiment,
    ToolCallTrace,
    ToolCompletedEvent,
    ToolError,
    ToolExecutionMetadata,
    ToolName,
    ToolStartedEvent,
    ToolStatus,
)
from backend.app.api.ask import (
    AskRequest,
    get_conversation_service,
    get_request_identity,
    stream_ask_events,
)
from backend.app.core.database import get_db
from backend.app.db.repositories.schemas import ChatSessionRead
from backend.app.main import app

SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
USER_MESSAGE_ID = UUID("20000000-0000-0000-0000-000000000001")
ASSISTANT_MESSAGE_ID = UUID("30000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 31, tzinfo=UTC)


def trace(
    call_id: str,
    tool_name: str,
    status: ToolStatus = ToolStatus.SUCCESS,
    *,
    error: ToolError | None = None,
    result_count: int = 2,
) -> ToolCallTrace:
    return ToolCallTrace(
        call_id=call_id,
        tool_name=tool_name,
        arguments={},
        normalized_arguments={},
        executed=True,
        status=status,
        duration_ms=12,
        result_count=result_count,
        error=error,
    )


def citation(mention_id: UUID | None = None) -> AnswerCitation:
    document_id = uuid4()
    return AnswerCitation(
        mention_id=mention_id or uuid4(),
        document_id=document_id,
        evidence_preview="The fan is noticeable while charging.",
        sku_code="ecoflow-delta2",
        aspect_label="noise_level",
        sentiment=Sentiment.NEGATIVE,
        week_id=202631,
        source=ExpandedSourceMetadata(
            document_id=document_id,
            sku_code="ecoflow-delta2",
            platform="reddit",
            published_at=NOW,
            source_url="https://example.test/review/1",
            title="Charging noise",
            review_text="The fan is noticeable while charging, but it stops later.",
        ),
    )


def agent_result(
    traces: list[ToolCallTrace],
    *,
    status: AgentStatus = AgentStatus.SUCCESS,
    answer: str = "Supported VOC answer.",
    citations: list[AnswerCitation] | None = None,
    error: ToolError | None = None,
) -> AgentRunResult:
    return AgentRunResult(
        status=status,
        final_answer=answer,
        error=error,
        citations=citations or [],
        tool_trace=traces,
        execution=AgentExecutionMetadata(
            model_round_count=2,
            attempted_tool_call_count=len(traces),
            executed_tool_call_count=sum(item.executed for item in traces),
            maximum_tool_calls=3,
        ),
    )


class FakeConversationService:
    def __init__(self, result: AgentRunResult | Exception) -> None:
        self.result = result
        self.created_by: str | None = None
        self.created = 0
        self.turns: list[tuple[UUID | str, str]] = []

    async def create_session(
        self, *, title: str | None = None, created_by: str | None = None
    ) -> ChatSessionRead:
        self.created += 1
        self.created_by = created_by
        return ChatSessionRead(
            id=SESSION_ID,
            title=title,
            created_by=created_by,
            is_active=True,
            created_at=NOW,
            updated_at=NOW,
        )

    async def run_turn(
        self,
        *,
        session_id: UUID | str,
        user_message: str,
        event_sink=None,
    ) -> ConversationTurnResult:
        self.turns.append((session_id, user_message))
        if isinstance(self.result, Exception):
            raise self.result
        if event_sink is not None:
            for item in self.result.tool_trace:
                if not item.executed:
                    continue
                await event_sink(
                    ToolStartedEvent(
                        call_id=item.call_id,
                        tool_name=ToolName(item.tool_name),
                    )
                )
                await event_sink(
                    ToolCompletedEvent(
                        call_id=item.call_id,
                        tool_name=ToolName(item.tool_name),
                        status=item.status,
                        warnings=item.warnings,
                        execution=ToolExecutionMetadata(
                            duration_ms=item.duration_ms,
                            result_count=item.result_count,
                            call_id=item.call_id,
                        ),
                    )
                )
        return ConversationTurnResult(
            session_id=UUID(str(session_id)),
            user_message_id=USER_MESSAGE_ID,
            assistant_message_id=ASSISTANT_MESSAGE_ID,
            agent_result=self.result,
        )


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event_type = lines[0].removeprefix("event: ")
        payload = json.loads(lines[1].removeprefix("data: "))
        events.append((event_type, payload))
    return events


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.commit_error: Exception | None = None
        self.rollback_error: Exception | None = None

    async def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error


@pytest.fixture
def api_client(
) -> Iterator[tuple[TestClient, FakeConversationService, FakeTransaction]]:
    service = FakeConversationService(agent_result([trace("sql-1", "tool_sql")]))
    transaction = FakeTransaction()
    app.dependency_overrides[get_conversation_service] = lambda: service
    app.dependency_overrides[get_request_identity] = lambda: "phase7-test"
    app.dependency_overrides[get_db] = lambda: transaction
    client = TestClient(app, raise_server_exceptions=False)
    yield client, service, transaction
    client.close()
    app.dependency_overrides.clear()


def test_new_session_is_created_and_done_contains_stable_ids(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, service, transaction = api_client

    response = client.post("/api/ask", json={"message": "Count Delta 2 reviews"})
    events = parse_sse(response.text)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert service.created == 1
    assert service.created_by == "phase7-test"
    assert service.turns == [(SESSION_ID, "Count Delta 2 reviews")]
    assert transaction.commits == 1
    assert transaction.rollbacks == 0
    assert events[-1] == (
        "done",
        {
            "event_type": "done",
            "session_id": str(SESSION_ID),
            "user_message_id": str(USER_MESSAGE_ID),
            "assistant_message_id": str(ASSISTANT_MESSAGE_ID),
            "status": "success",
        },
    )


def test_existing_session_is_reused_without_creation(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, service, _ = api_client

    response = client.post(
        "/api/ask",
        json={"session_id": str(SESSION_ID), "message": "What about noise?"},
    )

    assert response.status_code == 200
    assert service.created == 0
    assert service.turns == [(SESSION_ID, "What about noise?")]


@pytest.mark.parametrize(
    ("traces", "expected"),
    [
        (
            [trace("sql-1", "tool_sql")],
            ["tool_started", "tool_completed", "answer_delta", "done"],
        ),
        (
            [trace("rag-1", "tool_rag")],
            ["tool_started", "tool_completed", "answer_delta", "done"],
        ),
        (
            [trace("sql-1", "tool_sql"), trace("rag-1", "tool_rag")],
            [
                "tool_started",
                "tool_completed",
                "tool_started",
                "tool_completed",
                "answer_delta",
                "done",
            ],
        ),
    ],
)
def test_tool_event_sequences(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
    traces: list[ToolCallTrace],
    expected: list[str],
) -> None:
    client, service, _ = api_client
    service.result = agent_result(traces)

    response = client.post("/api/ask", json={"message": "Analyze VOC"})
    events = parse_sse(response.text)

    assert [name for name, _ in events] == expected
    completed = [payload for name, payload in events if name == "tool_completed"]
    assert [item["call_id"] for item in completed] == [item.call_id for item in traces]
    assert all(item["execution"]["duration_ms"] == 12 for item in completed)


def test_only_final_answer_citations_are_emitted(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, service, _ = api_client
    used = citation()
    unused_retrieved_id = uuid4()
    service.result = agent_result(
        [trace("rag-1", "tool_rag", result_count=8)],
        citations=[used],
    )

    response = client.post("/api/ask", json={"message": "Show actual comments"})
    events = parse_sse(response.text)
    citation_payloads = [payload for name, payload in events if name == "citation"]

    assert [name for name, _ in events] == [
        "tool_started",
        "tool_completed",
        "answer_delta",
        "citation",
        "done",
    ]
    assert [item["citation"]["mention_id"] for item in citation_payloads] == [
        str(used.mention_id)
    ]
    assert str(unused_retrieved_id) not in response.text
    assert citation_payloads[0]["citation"]["source"]["document_id"] == str(
        used.document_id
    )


def test_partial_failure_streams_supported_answer_without_citations(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, service, _ = api_client
    rag_error = ToolError(
        code="rag_search_failed",
        message="Review evidence is temporarily unavailable.",
        retryable=True,
    )
    service.result = agent_result(
        [
            trace("sql-1", "tool_sql"),
            trace("rag-1", "tool_rag", ToolStatus.ERROR, error=rag_error, result_count=0),
        ],
        status=AgentStatus.PARTIAL,
        answer=(
            "The quantitative distribution is available. "
            "Supporting review evidence is temporarily unavailable."
        ),
    )

    response = client.post("/api/ask", json={"message": "Metrics and comments"})
    events = parse_sse(response.text)

    assert [name for name, _ in events] == [
        "tool_started",
        "tool_completed",
        "tool_started",
        "tool_completed",
        "answer_delta",
        "done",
    ]
    assert events[3][1]["status"] == "error"
    assert events[-1][1]["status"] == "partial"
    assert "temporarily unavailable" in response.text
    assert "citation" not in [name for name, _ in events]


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (UnknownSessionError("missing"), "unknown_session"),
        (RuntimeError("secret database detail"), "request_failed"),
    ],
)
def test_request_failure_is_a_safe_terminal_error_event(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
    failure: Exception,
    expected_code: str,
) -> None:
    client, service, transaction = api_client
    service.result = failure

    response = client.post(
        "/api/ask",
        json={"session_id": str(SESSION_ID), "message": "Analyze VOC"},
    )
    events = parse_sse(response.text)

    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["error"]["code"] == expected_code
    assert "secret database detail" not in response.text
    assert transaction.commits == 0
    assert transaction.rollbacks == 1


def test_agent_error_emits_tool_facts_then_terminal_error(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, service, transaction = api_client
    tool_error = ToolError(code="analytics_failed", message="Analytics unavailable.")
    service.result = agent_result(
        [trace("sql-1", "tool_sql", ToolStatus.ERROR, error=tool_error)],
        status=AgentStatus.ERROR,
        answer="The request could not be completed.",
    )

    response = client.post("/api/ask", json={"message": "Analyze VOC"})
    events = parse_sse(response.text)

    assert [name for name, _ in events] == [
        "tool_started",
        "tool_completed",
        "error",
    ]
    assert events[-1][1]["error"]["code"] == "analytics_failed"
    assert transaction.commits == 1


def test_agent_level_error_uses_safe_structured_category(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, service, _ = api_client
    service.result = agent_result(
        [],
        status=AgentStatus.ERROR,
        answer="The language model is temporarily unavailable.",
        error=ToolError(
            code="llm_timeout",
            message="The language model is temporarily unavailable.",
            retryable=True,
        ),
    )

    response = client.post("/api/ask", json={"message": "Analyze VOC"})
    events = parse_sse(response.text)

    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["error"] == {
        "code": "llm_timeout",
        "message": "The language model is temporarily unavailable.",
        "retryable": True,
        "details": {},
    }


def test_request_validation_rejects_blank_and_extra_fields(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, service, transaction = api_client

    blank = client.post("/api/ask", json={"message": "   "})
    extra = client.post("/api/ask", json={"message": "hello", "active_sku": "x"})

    assert blank.status_code == 422
    assert extra.status_code == 422
    assert service.turns == []
    assert transaction.commits == 0


def test_commit_failure_emits_error_instead_of_successful_done(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, _, transaction = api_client
    transaction.commit_error = RuntimeError("commit failed")

    response = client.post("/api/ask", json={"message": "Analyze VOC"})
    events = parse_sse(response.text)

    assert [name for name, _ in events] == [
        "tool_started",
        "tool_completed",
        "error",
    ]
    assert transaction.rollbacks == 1


def test_rollback_failure_does_not_hide_structured_request_error(
    api_client: tuple[TestClient, FakeConversationService, FakeTransaction],
) -> None:
    client, service, transaction = api_client
    service.result = RuntimeError("request failed")
    transaction.rollback_error = RuntimeError("rollback failed")

    response = client.post(
        "/api/ask",
        json={"session_id": str(SESSION_ID), "message": "Analyze VOC"},
    )
    events = parse_sse(response.text)

    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["error"]["code"] == "request_failed"


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


class BlockingService(FakeConversationService):
    def __init__(self) -> None:
        super().__init__(agent_result([]))
        self.started = asyncio.Event()

    async def run_turn(
        self,
        *,
        session_id: UUID | str,
        user_message: str,
        event_sink=None,
    ) -> ConversationTurnResult:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class LiveLifecycleService(FakeConversationService):
    def __init__(self) -> None:
        super().__init__(agent_result([trace("sql-live", "tool_sql")]))
        self.release = asyncio.Event()
        self.finished = False

    async def run_turn(
        self,
        *,
        session_id: UUID | str,
        user_message: str,
        event_sink=None,
    ) -> ConversationTurnResult:
        assert event_sink is not None
        await event_sink(
            ToolStartedEvent(call_id="sql-live", tool_name=ToolName.SQL)
        )
        await self.release.wait()
        await event_sink(
            ToolCompletedEvent(
                call_id="sql-live",
                tool_name=ToolName.SQL,
                status=ToolStatus.SUCCESS,
            )
        )
        self.finished = True
        return ConversationTurnResult(
            session_id=UUID(str(session_id)),
            user_message_id=USER_MESSAGE_ID,
            assistant_message_id=ASSISTANT_MESSAGE_ID,
            agent_result=self.result,
        )


async def test_tool_started_is_streamed_before_the_tool_finishes() -> None:
    service = LiveLifecycleService()
    transaction = FakeTransaction()
    stream = stream_ask_events(
        payload=AskRequest(session_id=SESSION_ID, message="Analyze VOC"),
        service=service,  # type: ignore[arg-type]
        created_by=None,
        request=ConnectedRequest(),  # type: ignore[arg-type]
        transaction=transaction,
    )

    first = await anext(stream)

    assert parse_sse(first)[0][0] == "tool_started"
    assert service.finished is False
    assert transaction.commits == 0

    service.release.set()
    remaining = [item async for item in stream]
    remaining_events = parse_sse("".join(remaining))
    assert [name for name, _ in remaining_events] == [
        "tool_completed",
        "answer_delta",
        "done",
    ]
    assert transaction.commits == 1


async def test_stream_cancellation_propagates_to_in_flight_agent_work() -> None:
    service = BlockingService()
    stream = stream_ask_events(
        payload=AskRequest(session_id=SESSION_ID, message="Analyze VOC"),
        service=service,  # type: ignore[arg-type]
        created_by=None,
        request=ConnectedRequest(),  # type: ignore[arg-type]
        transaction=FakeTransaction(),
    )
    pending = asyncio.create_task(anext(stream))
    await service.started.wait()

    pending.cancel()

    with pytest.raises(asyncio.CancelledError):
        await pending
    await stream.aclose()
