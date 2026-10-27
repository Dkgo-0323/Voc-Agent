"""Authenticated SSE transport for bounded weekly report generation."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

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
from backend.app.core.database import get_db
from backend.app.core.model_resources import model_resources, stop_acceptance_run
from backend.app.core.security import get_request_identity
from backend.app.db.repositories.analytics_repo import AnalyticsRepository
from backend.app.db.repositories.evidence_repo import EvidenceRepository
from backend.app.db.repositories.report_repo import ReportRepository
from backend.app.reporting.service import (
    GenerateReportArguments,
    ReportGenerationFailure,
    ReportGenerationService,
)
from pipelines.embedding.milvus_repo import MilvusRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["Reports"])
REPORT_CHUNK_SIZE = 240


class RequestTransaction(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


async def get_report_generation_service(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[ReportGenerationService, None]:
    async with model_resources(request.app) as resources:
        analytics = AnalyticsService(
            cast(AnalyticsRepositoryProtocol, AnalyticsRepository(db))
        )
        rag = RagRetrievalService(
            EvidenceRepository(db),
            resources.embedder,
            MilvusRepository(),
        )
        yield ReportGenerationService(ReportRepository(db), analytics, rag, resources.chat)


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

    completed = False
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
        terminal = _sse(ReportCompletedEvent(report=report))
        completed = True
        yield terminal
    except asyncio.CancelledError:
        stop_acceptance_run(request)
        await _rollback_quietly(transaction)
        raise
    except GeneratorExit:
        if not completed:
            stop_acceptance_run(request)
            await _rollback_quietly(transaction)
        raise
    except ReportGenerationFailure as exc:
        stop_acceptance_run(request)
        await _rollback_quietly(transaction)
        yield _sse(ReportErrorEvent(error=exc.error))
    except Exception:
        stop_acceptance_run(request)
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
    finally:
        if not completed:
            stop_acceptance_run(request)


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
