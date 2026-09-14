"""Thin SSE transport for the already-working conversation Agent service."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import suppress
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.conversation import ConversationService, UnknownSessionError
from backend.app.agent.llm import OpenAIChatCompletionsModel
from backend.app.agent.router import (
    VOC_SYSTEM_POLICY,
    FunctionCallingRouter,
    build_tool_bindings,
)
from backend.app.agent.schemas import (
    AgentStatus,
    AnswerDeltaEvent,
    CitationEvent,
    DoneEvent,
    ErrorEvent,
    StreamingEvent,
    ToolError,
)
from backend.app.agent.tool_rag import RagRetrievalService
from backend.app.agent.tool_report import ReportService
from backend.app.agent.tool_sql import AnalyticsService
from backend.app.core.database import get_db
from backend.app.core.security import get_request_identity
from backend.app.core.settings import settings
from backend.app.db.repositories.analytics_repo import AnalyticsRepository
from backend.app.db.repositories.conversation_repo import ConversationRepository
from backend.app.db.repositories.evidence_repo import EvidenceRepository
from backend.app.db.repositories.report_repo import ReportRepository
from pipelines.embedding.embedder import Embedder
from pipelines.embedding.milvus_repo import MilvusRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Agent"])

ANSWER_CHUNK_SIZE = 240


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID | None = None
    message: str = Field(min_length=1, max_length=10_000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


def _normalized_base_url(value: str) -> str:
    return value.rstrip("/").lower()


def _uses_zhipu_json_mode() -> bool:
    return "bigmodel.cn" in _normalized_base_url(settings.llm_base_url)


def _resolve_llm_api_key() -> str:
    """Reuse the embedding key only when both clients target the same provider."""
    if settings.llm_api_key:
        return settings.llm_api_key
    if _normalized_base_url(settings.llm_base_url) == _normalized_base_url(
        settings.embedding_base_url
    ):
        return settings.embedding_api_key
    if "api.openai.com" in settings.llm_base_url:
        return settings.openai_api_key
    return ""


async def get_conversation_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[ConversationService, None]:
    """Build request-scoped services while keeping tool wiring out of the endpoint."""

    llm_key = _resolve_llm_api_key()
    embedding_key = settings.embedding_api_key or settings.openai_api_key
    if not llm_key:
        raise RuntimeError(
            "LLM_API_KEY is not configured and no same-provider key can be reused"
        )
    llm_client = AsyncOpenAI(
        api_key=llm_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    embedding_client = AsyncOpenAI(
        api_key=embedding_key,
        base_url=settings.embedding_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    try:
        analytics_service = AnalyticsService(AnalyticsRepository(db))
        report_service = ReportService(ReportRepository(db))
        rag_service = RagRetrievalService(
            EvidenceRepository(db),
            Embedder(client=embedding_client),
            MilvusRepository(),
        )
        model = OpenAIChatCompletionsModel(
            llm_client,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            extra_body=settings.llm_extra_body,
            final_response_format=(
                {"type": "json_object"} if _uses_zhipu_json_mode() else None
            ),
        )
        agent_router = FunctionCallingRouter(
            model,
            build_tool_bindings(
                report_service=report_service,
                analytics_service=analytics_service,
                rag_service=rag_service,
            ),
            system_policy=VOC_SYSTEM_POLICY,
        )
        yield ConversationService(ConversationRepository(db), agent_router)
    finally:
        await llm_client.close()
        await embedding_client.close()


ConversationDependency = Annotated[
    ConversationService, Depends(get_conversation_service)
]
IdentityDependency = Annotated[str, Depends(get_request_identity)]
DatabaseDependency = Annotated[AsyncSession, Depends(get_db)]


class RequestTransaction(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


async def _rollback_quietly(transaction: RequestTransaction) -> None:
    try:
        await transaction.rollback()
    except Exception:
        logger.exception("Failed to roll back Agent request transaction")


def _sse(event: StreamingEvent) -> str:
    payload = event.model_dump(mode="json")
    return (
        f"event: {event.event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _answer_chunks(answer: str) -> list[str]:
    return [
        answer[offset : offset + ANSWER_CHUNK_SIZE]
        for offset in range(0, len(answer), ANSWER_CHUNK_SIZE)
    ]


async def stream_ask_events(
    *,
    payload: AskRequest,
    service: ConversationService,
    created_by: str | None,
    request: Request,
    transaction: RequestTransaction,
) -> AsyncIterator[str]:
    """Map persisted Agent results to the public SSE contract."""

    try:
        if await request.is_disconnected():
            return
        session_id = payload.session_id
        if session_id is None:
            session = await service.create_session(created_by=created_by)
            session_id = session.id

        lifecycle_events: asyncio.Queue[StreamingEvent] = asyncio.Queue()

        async def capture_event(event: StreamingEvent) -> None:
            await lifecycle_events.put(event)

        turn_task = asyncio.create_task(
            service.run_turn(
                session_id=session_id,
                user_message=payload.message,
                event_sink=capture_event,
            )
        )
        while not turn_task.done():
            next_event = asyncio.create_task(lifecycle_events.get())
            completed, _ = await asyncio.wait(
                {turn_task, next_event},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if next_event in completed:
                yield _sse(next_event.result())
            else:
                next_event.cancel()
                with suppress(asyncio.CancelledError):
                    await next_event
        while not lifecycle_events.empty():
            yield _sse(lifecycle_events.get_nowait())

        turn = await turn_task
        result = turn.agent_result
        await transaction.commit()

        if result.status is AgentStatus.ERROR:
            trace_error = next(
                (
                    trace.error
                    for trace in reversed(result.tool_trace)
                    if trace.error is not None
                ),
                None,
            )
            yield _sse(
                ErrorEvent(
                    error=result.error
                    or trace_error
                    or ToolError(
                        code="agent_request_failed",
                        message="The VOC request could not be completed.",
                        retryable=True,
                    )
                )
            )
            return

        for delta in _answer_chunks(result.final_answer):
            yield _sse(AnswerDeltaEvent(delta=delta))
        for citation in result.citations:
            yield _sse(CitationEvent(citation=citation))
        yield _sse(
            DoneEvent(
                session_id=turn.session_id,
                user_message_id=turn.user_message_id,
                assistant_message_id=turn.assistant_message_id,
                status=result.status,
            )
        )
    except asyncio.CancelledError:
        if "turn_task" in locals() and not turn_task.done():
            turn_task.cancel()
            with suppress(asyncio.CancelledError):
                await turn_task
        await _rollback_quietly(transaction)
        raise
    except UnknownSessionError:
        await _rollback_quietly(transaction)
        yield _sse(
            ErrorEvent(
                error=ToolError(
                    code="unknown_session",
                    message="The chat session does not exist or is inactive.",
                )
            )
        )
    except ValueError:
        await _rollback_quietly(transaction)
        yield _sse(
            ErrorEvent(
                error=ToolError(
                    code="invalid_request",
                    message="The request could not be validated.",
                )
            )
        )
    except Exception:
        await _rollback_quietly(transaction)
        logger.exception("Agent request failed")
        yield _sse(
            ErrorEvent(
                error=ToolError(
                    code="request_failed",
                    message="The VOC service is temporarily unavailable.",
                    retryable=True,
                )
            )
        )


@router.post("/ask")
async def ask(
    payload: AskRequest,
    request: Request,
    service: ConversationDependency,
    identity: IdentityDependency,
    db: DatabaseDependency,
) -> StreamingResponse:
    return StreamingResponse(
        stream_ask_events(
            payload=payload,
            service=service,
            created_by=identity,
            request=request,
            transaction=db,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
