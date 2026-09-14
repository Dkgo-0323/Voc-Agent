"""Conversation orchestration over PostgreSQL recent-message history."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from backend.app.agent.schemas import (
    AgentRunResult,
    ConversationMessage,
    ConversationTurnResult,
    ToolCompletedEvent,
    ToolStartedEvent,
)
from backend.app.core.settings import settings
from backend.app.db.repositories.schemas import (
    ChatMessageRead,
    ChatSessionRead,
    PersistedTurnRow,
)


class UnknownSessionError(LookupError):
    pass


class ConversationRepositoryProtocol(Protocol):
    async def create_session(
        self, *, title: str | None = None, created_by: str | None = None
    ) -> ChatSessionRead: ...

    async def get_session(self, session_id: UUID) -> ChatSessionRead | None: ...

    async def get_recent_messages(
        self, session_id: UUID, *, limit: int
    ) -> list[ChatMessageRead]: ...

    async def persist_turn(
        self,
        *,
        session_id: UUID,
        user_content: str,
        assistant_content: str,
        tool_calls: dict[str, Any],
        tool_results: dict[str, Any],
        cited_ids: dict[str, Any],
    ) -> PersistedTurnRow: ...


class RouterProtocol(Protocol):
    async def run(
        self,
        *,
        recent_messages: list[ConversationMessage],
        current_user_message: str,
        event_sink: ToolLifecycleSink | None = None,
    ) -> AgentRunResult: ...


ToolLifecycleSink = Callable[
    [ToolStartedEvent | ToolCompletedEvent], Awaitable[None]
]


class ConversationService:
    def __init__(
        self,
        repository: ConversationRepositoryProtocol,
        router: RouterProtocol,
        *,
        recent_message_limit: int = settings.recent_message_limit,
    ) -> None:
        if recent_message_limit < 1:
            raise ValueError("recent_message_limit must be positive")
        self._repository = repository
        self._router = router
        self._recent_message_limit = recent_message_limit

    async def create_session(
        self, *, title: str | None = None, created_by: str | None = None
    ) -> ChatSessionRead:
        return await self._repository.create_session(
            title=title.strip() if title else None,
            created_by=created_by.strip() if created_by else None,
        )

    async def run_turn(
        self,
        *,
        session_id: UUID | str,
        user_message: str,
        event_sink: ToolLifecycleSink | None = None,
    ) -> ConversationTurnResult:
        resolved_session_id = self._parse_session_id(session_id)
        if not user_message.strip():
            raise ValueError("user_message must not be blank")
        chat_session = await self._repository.get_session(resolved_session_id)
        if chat_session is None:
            raise UnknownSessionError("chat session does not exist or is inactive")
        stored_messages = await self._repository.get_recent_messages(
            resolved_session_id,
            limit=self._recent_message_limit,
        )
        recent_messages = [self._visible_message(item) for item in stored_messages]
        router_arguments = {
            "recent_messages": recent_messages,
            "current_user_message": user_message.strip(),
        }
        if event_sink is None:
            agent_result = await self._router.run(**router_arguments)
        else:
            agent_result = await self._router.run(
                **router_arguments,
                event_sink=event_sink,
            )
        persisted = await self._repository.persist_turn(
            session_id=resolved_session_id,
            user_content=user_message.strip(),
            assistant_content=agent_result.final_answer,
            tool_calls=self._compact_tool_calls(agent_result),
            tool_results=self._compact_tool_results(agent_result),
            cited_ids={
                "mention_ids": [
                    str(citation.mention_id) for citation in agent_result.citations
                ]
            },
        )
        return ConversationTurnResult(
            session_id=resolved_session_id,
            user_message_id=persisted.user_message_id,
            assistant_message_id=persisted.assistant_message_id,
            agent_result=agent_result,
        )

    @staticmethod
    def _parse_session_id(session_id: UUID | str) -> UUID:
        if isinstance(session_id, UUID):
            return session_id
        try:
            return UUID(session_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("session_id must be a valid UUID") from exc

    @staticmethod
    def _visible_message(message: ChatMessageRead) -> ConversationMessage:
        if message.role not in {"user", "assistant"}:
            raise ValueError("stored chat message has an unsupported role")
        return ConversationMessage(role=message.role, content=message.content)

    @staticmethod
    def _compact_tool_calls(result: AgentRunResult) -> dict[str, Any]:
        return {
            "version": 1,
            "calls": [
                {
                    "call_id": trace.call_id,
                    "tool_name": trace.tool_name,
                    "executed": trace.executed,
                    "normalized_arguments": trace.normalized_arguments,
                }
                for trace in result.tool_trace
            ],
        }

    @staticmethod
    def _compact_tool_results(result: AgentRunResult) -> dict[str, Any]:
        return {
            "version": 1,
            "agent_status": result.status.value,
            "agent_error": (
                {
                    "code": result.error.code,
                    "retryable": result.error.retryable,
                }
                if result.error is not None
                else None
            ),
            "execution": result.execution.model_dump(mode="json"),
            "results": [
                {
                    "call_id": trace.call_id,
                    "tool_name": trace.tool_name,
                    "status": trace.status.value,
                    "result_count": trace.result_count,
                    "duration_ms": trace.duration_ms,
                    "warnings": [
                        warning.model_dump(mode="json") for warning in trace.warnings
                    ],
                    "error": (
                        {
                            "code": trace.error.code,
                            "retryable": trace.error.retryable,
                        }
                        if trace.error is not None
                        else None
                    ),
                }
                for trace in result.tool_trace
            ],
        }
