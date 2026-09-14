"""Grounded weekly report generation with deterministic inputs and validated output."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from backend.app.agent.llm import ChatModelProtocol
from backend.app.agent.schemas import (
    AnalyticsOperation,
    AnalyticsToolArguments,
    RagToolArguments,
    Sentiment,
    ToolError,
    ToolStatus,
    WeeklyReportPayload,
    WeekRange,
)
from backend.app.agent.tool_rag import RagRetrievalService
from backend.app.agent.tool_sql import AnalyticsService
from backend.app.db.repositories.schemas import SkuMetadata, WeeklyReportRow
from pipelines.config.targets import LOCKED_SKU_CODES


class GenerateReportArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_code: str = Field(min_length=1)
    week_id: int = Field(ge=1)

    @field_validator("sku_code")
    @classmethod
    def normalize_sku_code(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("sku_code must not be blank")
        return value


class ReportCandidate(BaseModel):
    """The only model-controlled data persisted for a generated report."""

    model_config = ConfigDict(extra="forbid")

    report_md: str = Field(min_length=120, max_length=16_000)
    summary: str = Field(min_length=20, max_length=1_200)

    @field_validator("report_md")
    @classmethod
    def require_bounded_sections(cls, value: str) -> str:
        required = (
            "## Executive Summary",
            "## Key Metrics",
            "## Positive Themes",
            "## Negative Themes",
            "## SKU Highlights",
            "## Competitor Observations",
        )
        if any(section not in value for section in required):
            raise ValueError("report_md must contain the required report sections")
        return value.strip()


class ReportRepositoryProtocol(Protocol):
    async def get_enabled_skus(self) -> list[SkuMetadata]: ...

    async def save_weekly_report(
        self,
        *,
        sku_code: str,
        week_id: int,
        report_md: str,
        summary: str,
    ) -> WeeklyReportRow: ...


class ReportGenerationFailure(RuntimeError):
    def __init__(self, error: ToolError) -> None:
        super().__init__(error.message)
        self.error = error


class ReportGenerationService:
    """Collect approved facts, synthesize a bounded candidate, then stage persistence."""

    def __init__(
        self,
        repository: ReportRepositoryProtocol,
        analytics: AnalyticsService,
        rag: RagRetrievalService,
        model: ChatModelProtocol,
    ) -> None:
        self._repository = repository
        self._analytics = analytics
        self._rag = rag
        self._model = model

    async def collect_analytics(self, arguments: GenerateReportArguments) -> dict[str, Any]:
        self._validate_week(arguments.week_id)
        await self._validate_sku(arguments.sku_code)
        week_range = WeekRange(
            start_week_id=arguments.week_id,
            end_week_id=arguments.week_id,
        )
        metrics: dict[str, Any] = {}
        warnings: list[str] = []
        for operation in (
            AnalyticsOperation.REVIEW_COUNT,
            AnalyticsOperation.SENTIMENT_DISTRIBUTION,
            AnalyticsOperation.ASPECT_DISTRIBUTION,
        ):
            result = await self._analytics.execute(
                AnalyticsToolArguments(
                    operation=operation,
                    sku_codes=[arguments.sku_code],
                    week_range=week_range,
                    limit=6,
                )
            )
            if result.status is ToolStatus.ERROR:
                raise ReportGenerationFailure(
                    ToolError(
                        code="report_analytics_failed",
                        message="Report analytics are temporarily unavailable.",
                        retryable=bool(result.error and result.error.retryable),
                    )
                )
            if result.status is ToolStatus.EMPTY or result.payload is None:
                raise ReportGenerationFailure(
                    ToolError(
                        code="report_not_possible",
                        message="No quality-qualified VOC data is available for this SKU and week.",
                    )
                )
            warnings.extend(warning.message for warning in result.warnings)
            metrics[operation.value] = result.payload.model_dump(mode="json")

        return {
            "sku_code": arguments.sku_code,
            "week_id": arguments.week_id,
            "metrics": metrics,
            "evidence": [],
            "warnings": warnings,
        }

    async def retrieve_evidence(self, facts: dict[str, Any]) -> dict[str, Any]:
        sku_code = facts["sku_code"]
        week_id = facts["week_id"]
        week_range = WeekRange(start_week_id=week_id, end_week_id=week_id)
        evidence: list[dict[str, Any]] = []
        warnings = list(facts["warnings"])
        for sentiment, query in (
            (Sentiment.POSITIVE, "representative positive customer experience"),
            (Sentiment.NEGATIVE, "representative customer complaint or limitation"),
        ):
            result = await self._rag.execute(
                RagToolArguments(
                    query=query,
                    sku_codes=[sku_code],
                    week_range=week_range,
                    sentiment=sentiment,
                    top_k=2,
                )
            )
            if result.status is ToolStatus.ERROR:
                raise ReportGenerationFailure(
                    ToolError(
                        code="report_retrieval_failed",
                        message="Report evidence retrieval is temporarily unavailable.",
                        retryable=bool(result.error and result.error.retryable),
                    )
                )
            if result.payload is None:
                warnings.append(f"No {sentiment.value} representative evidence was retrieved.")
                continue
            for item in result.payload.evidence:
                evidence.append(
                    {
                        "aspect_label": item.aspect_label,
                        "sentiment": item.sentiment.value,
                        "mention_text": item.mention_text,
                    }
                )
        return {**facts, "evidence": evidence, "warnings": warnings}

    async def synthesize(self, facts: dict[str, Any]) -> ReportCandidate:
        prompt = {
            "role": "user",
            "content": (
                "Write a bounded weekly VOC report using only the supplied facts. "
                "Never invent metrics, customer quotes, competitors, causes, or recommendations. "
                "Do not include citation IDs, source URLs, or an Evidence/Citations section: "
                "the current report schema has no durable report-to-mention relation. "
                "Use exactly these Markdown headings: ## Executive Summary, ## Key Metrics, "
                "## Positive Themes, ## Negative Themes, ## SKU Highlights, "
                "## Competitor Observations. If comparison data is not supplied, say so plainly. "
                "Return only JSON with exactly report_md and summary.\n\n"
                + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
            ),
        }
        try:
            response = await self._model.complete(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a constrained VOC report writer. Output valid JSON only.",
                    },
                    prompt,
                ],
                tools=[],
            )
            raw = response.content
            if not raw:
                raise ValueError("empty model response")
            return ReportCandidate.model_validate_json(raw)
        except (ValueError, TypeError, json.JSONDecodeError):
            raise ReportGenerationFailure(
                ToolError(
                    code="report_validation_failed",
                    message="The generated report did not satisfy the required structure.",
                )
            ) from None
        except Exception:
            raise ReportGenerationFailure(
                ToolError(
                    code="llm_request_failed",
                    message="The report writer is temporarily unavailable.",
                    retryable=True,
                )
            ) from None

    async def persist(
        self,
        arguments: GenerateReportArguments,
        candidate: ReportCandidate,
    ) -> WeeklyReportPayload:
        try:
            row = await self._repository.save_weekly_report(
                sku_code=arguments.sku_code,
                week_id=arguments.week_id,
                report_md=candidate.report_md,
                summary=candidate.summary,
            )
        except (SQLAlchemyError, ConnectionError, TimeoutError):
            raise ReportGenerationFailure(
                ToolError(
                    code="report_persistence_failed",
                    message="The report could not be saved. The previous report was preserved.",
                    retryable=True,
                )
            ) from None
        return WeeklyReportPayload(**row.model_dump())

    async def _validate_sku(self, sku_code: str) -> None:
        try:
            enabled = await self._repository.get_enabled_skus()
        except (SQLAlchemyError, ConnectionError, TimeoutError):
            raise ReportGenerationFailure(
                ToolError(
                    code="report_query_failed",
                    message="Report scope validation is temporarily unavailable.",
                    retryable=True,
                )
            ) from None
        allowed = {sku.sku_code for sku in enabled if sku.sku_code in LOCKED_SKU_CODES}
        if sku_code not in allowed:
            raise ReportGenerationFailure(
                ToolError(
                    code="unknown_or_disabled_sku",
                    message="SKU is not locked and dashboard-enabled.",
                    details={"sku_code": sku_code},
                )
            )

    @staticmethod
    def _validate_week(week_id: int) -> None:
        year, week = divmod(week_id, 100)
        try:
            date.fromisocalendar(year, week, 1)
        except ValueError:
            raise ReportGenerationFailure(
                ToolError(
                    code="invalid_week_id",
                    message="week_id must be a valid ISO week identifier.",
                    details={"week_id": week_id},
                )
            ) from None
