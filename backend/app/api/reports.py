"""Authenticated SSE transport for bounded weekly report generation."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.llm import OpenAIChatCompletionsModel
from backend.app.agent.schemas import (
    ReportCompletedEvent,
    ReportDeltaEvent,
    ReportErrorEvent,
    ReportStageCompletedEvent,
    ReportStageStartedEvent,
    ReportStartedEvent,
    ReportStreamingEvent,
    ToolError,
)
from backend.app.agent.tool_rag import RagRetrievalService
from backend.app.agent.tool_sql import AnalyticsRepositoryProtocol, AnalyticsService
from backend.app.api.ask import _resolve_llm_api_key, _uses_zhipu_json_mode
from backend.app.core.database import get_db
from backend.app.core.security import get_request_identity
from backend.app.core.settings import settings
from backend.app.db.repositories.analytics_repo import AnalyticsRepository
from backend.app.db.repositories.evidence_repo import EvidenceRepository
from backend.app.db.repositories.report_repo import ReportRepository
from backend.app.reporting.service import (
    GenerateReportArguments,
    ReportGenerationFailure,
    ReportGenerationService,
)
from pipelines.embedding.embedder import Embedder
from pipelines.embedding.milvus_repo import MilvusRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["Reports"])
REPORT_CHUNK_SIZE = 240


class RequestTransaction(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


async def get_report_generation_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[ReportGenerationService, None]:
    llm_key = _resolve_llm_api_key()
    embedding_key = settings.embedding_api_key or settings.openai_api_key
    if not llm_key:
        raise RuntimeError("LLM_API_KEY is not configured")
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
        analytics = AnalyticsService(
            cast(AnalyticsRepositoryProtocol, AnalyticsRepository(db))
        )
        rag = RagRetrievalService(
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
        yield ReportGenerationService(ReportRepository(db), analytics, rag, model)
    finally:
        await llm_client.close()
        await embedding_client.close()


ReportGenerationDependency = Annotated[
    ReportGenerationService, Depends(get_report_generation_service)
]
IdentityDependency = Annotated[str, Depends(get_request_identity)]
DatabaseDependency = Annotated[AsyncSession, Depends(get_db)]


def _sse(event: ReportStreamingEvent) -> str:
    payload = event.model_dump(mode="json")
    return (
        f"event: {event.event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


async def _rollback_quietly(transaction: RequestTransaction) -> None:
    try:
        await transaction.rollback()
    except Exception:
        logger.exception("Failed to roll back report generation transaction")


async def stream_report_events(
    *,
    payload: GenerateReportArguments,
    service: ReportGenerationService,
    request: Request,
    transaction: RequestTransaction,
) -> AsyncIterator[str]:
    """Emit only safe progress; candidates are not completed until commit succeeds."""

    try:
        if await request.is_disconnected():
            return
        yield _sse(ReportStartedEvent(sku_code=payload.sku_code, week_id=payload.week_id))
        yield _sse(ReportStageStartedEvent(stage="collecting_analytics"))
        facts = await service.collect_analytics(payload)
        yield _sse(ReportStageCompletedEvent(stage="collecting_analytics"))
        yield _sse(ReportStageStartedEvent(stage="retrieving_evidence"))
        facts = await service.retrieve_evidence(facts)
        yield _sse(
            ReportStageCompletedEvent(
                stage="retrieving_evidence", warnings=facts["warnings"]
            )
        )
        yield _sse(ReportStageStartedEvent(stage="synthesizing"))
        candidate = await service.synthesize(facts)
        yield _sse(ReportStageCompletedEvent(stage="synthesizing"))
        yield _sse(ReportStageStartedEvent(stage="validating"))
        # Candidate Pydantic validation has already completed before any delta is sent.
        yield _sse(ReportStageCompletedEvent(stage="validating"))
        for offset in range(0, len(candidate.report_md), REPORT_CHUNK_SIZE):
            yield _sse(ReportDeltaEvent(delta=candidate.report_md[offset : offset + REPORT_CHUNK_SIZE]))
        yield _sse(ReportStageStartedEvent(stage="persisting"))
        report = await service.persist(payload, candidate)
        await transaction.commit()
        yield _sse(ReportStageCompletedEvent(stage="persisting"))
        yield _sse(ReportCompletedEvent(report=report))
    except asyncio.CancelledError:
        await _rollback_quietly(transaction)
        raise
    except ReportGenerationFailure as exc:
        await _rollback_quietly(transaction)
        yield _sse(ReportErrorEvent(error=exc.error))
    except Exception:
        await _rollback_quietly(transaction)
        logger.exception("Report generation failed")
        yield _sse(
            ReportErrorEvent(
                error=ToolError(
                    code="report_request_failed",
                    message="The weekly report could not be generated.",
                    retryable=True,
                )
            )
        )


@router.post("/generate")
async def generate_report(
    payload: GenerateReportArguments,
    request: Request,
    service: ReportGenerationDependency,
    _: IdentityDependency,
    db: DatabaseDependency,
) -> StreamingResponse:
    return StreamingResponse(
        stream_report_events(
            payload=payload,
            service=service,
            request=request,
            transaction=db,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
