"""PostgreSQL persistence for visible chat history and compact Agent metadata."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ChatMessage, ChatSession, utcnow
from backend.app.db.repositories.schemas import (
    ChatMessageRead,
    ChatSessionRead,
    PersistedTurnRow,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(
        self, *, title: str | None = None, created_by: str | None = None
    ) -> ChatSessionRead:
        chat_session = ChatSession(title=title, created_by=created_by, is_active=True)
        self._session.add(chat_session)
        await self._session.flush()
        return ChatSessionRead.model_validate(chat_session)

    async def get_session(self, session_id: UUID) -> ChatSessionRead | None:
        result = await self._session.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.is_active.is_(True),
            )
        )
        chat_session = result.scalar_one_or_none()
        return (
            ChatSessionRead.model_validate(chat_session)
            if chat_session is not None
            else None
        )

    async def get_recent_messages(
        self, session_id: UUID, *, limit: int
    ) -> list[ChatMessageRead]:
        if limit < 1:
            raise ValueError("limit must be positive")
        result = await self._session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        newest_first = [
            ChatMessageRead.model_validate(item) for item in result.scalars()
        ]
        return list(reversed(newest_first))

    async def persist_turn(
        self,
        *,
        session_id: UUID,
        user_content: str,
        assistant_content: str,
        tool_calls: dict[str, Any],
        tool_results: dict[str, Any],
        cited_ids: dict[str, Any],
    ) -> PersistedTurnRow:
        async with self._session.begin_nested():
            locked = await self._session.execute(
                select(ChatSession)
                .where(
                    ChatSession.id == session_id,
                    ChatSession.is_active.is_(True),
                )
                .with_for_update()
            )
            chat_session = locked.scalar_one_or_none()
            if chat_session is None:
                raise LookupError("chat session is missing or inactive")
            user_created_at = max(
                utcnow(), chat_session.updated_at + timedelta(microseconds=1)
            )
            assistant_created_at = user_created_at + timedelta(microseconds=1)
            user_message = ChatMessage(
                session_id=session_id,
                role="user",
                content=user_content,
                tool_calls=None,
                tool_results=None,
                cited_ids=None,
                created_at=user_created_at,
            )
            assistant_message = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=assistant_content,
                tool_calls=tool_calls,
                tool_results=tool_results,
                cited_ids=cited_ids,
                created_at=assistant_created_at,
            )
            self._session.add_all([user_message, assistant_message])
            chat_session.updated_at = assistant_created_at
            await self._session.flush()
        return PersistedTurnRow(
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
        )
