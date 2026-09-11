"""Typed contracts shared by the controlled Week 3 Agent tools.

These models define the boundary between the LLM-facing orchestration layer and
deterministic application code.  They deliberately contain no database, Milvus,
or model-client behavior.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class AgentSchema(BaseModel):
    """Base configuration for public Agent contracts."""

    model_config = ConfigDict(extra="forbid")


class ToolName(StrEnum):
    REPORT = "tool_report"
    SQL = "tool_sql"
    RAG = "tool_rag"


class ToolStatus(StrEnum):
    SUCCESS = "success"
    EMPTY = "empty"
    NOT_FOUND = "not_found"
    PARTIAL = "partial"
    ERROR = "error"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class AnalyticsOperation(StrEnum):
    REVIEW_COUNT = "review_count"
    SENTIMENT_DISTRIBUTION = "sentiment_distribution"
    ASPECT_DISTRIBUTION = "aspect_distribution"
    TREND = "trend"
    ASPECT_TREND = "aspect_trend"
    COMPARE_SKUS = "compare_skus"


class ComparisonMetric(StrEnum):
    MENTION_COUNT = "mention_count"
    POSITIVE_RATE = "positive_rate"
    NEGATIVE_RATE = "negative_rate"
    SENTIMENT_SCORE = "sentiment_score"


class WeekRange(AgentSchema):
    """Inclusive ISO-style integer week range (for example 202603)."""

    start_week_id: int = Field(ge=1)
    end_week_id: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> WeekRange:
        if self.start_week_id > self.end_week_id:
            raise ValueError("start_week_id must not exceed end_week_id")
        return self


def _validate_sku_codes(sku_codes: list[str]) -> list[str]:
    if any(not sku_code.strip() for sku_code in sku_codes):
        raise ValueError("sku_codes must not contain blank values")
    if len(set(sku_codes)) != len(sku_codes):
        raise ValueError("sku_codes must not contain duplicates")
    return sku_codes


class AnalyticsToolArguments(AgentSchema):
    """Structured request for the fixed analytics interface, never raw SQL."""

    operation: AnalyticsOperation
    sku_codes: list[str] = Field(default_factory=list)
    week_range: WeekRange | None = None
    aspect_label: str | None = Field(default=None, min_length=1)
    sentiment: Sentiment | None = None
    comparison_metric: ComparisonMetric | None = None
    limit: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def validate_operation_arguments(self) -> AnalyticsToolArguments:
        self.sku_codes = _validate_sku_codes(self.sku_codes)
        if (
            self.operation is AnalyticsOperation.COMPARE_SKUS
            and len(self.sku_codes) < 2
        ):
            raise ValueError("compare_skus requires at least two sku_codes")
        if self.operation is AnalyticsOperation.ASPECT_TREND and not self.aspect_label:
            raise ValueError("aspect_trend requires aspect_label")
        return self


class RagToolArguments(AgentSchema):
    """LLM-proposed retrieval filters, to be validated and enforced by the app."""

    query: str = Field(min_length=1)
    sku_codes: list[str] = Field(default_factory=list)
    week_range: WeekRange | None = None
    sentiment: Sentiment | None = None
    aspect_label: str | None = Field(default=None, min_length=1)
    top_k: int = Field(default=8, ge=1)

    @model_validator(mode="after")
    def validate_filters(self) -> RagToolArguments:
        self.sku_codes = _validate_sku_codes(self.sku_codes)
        if not self.query.strip():
            raise ValueError("query must not be blank")
        return self


class ReportToolArguments(AgentSchema):
    """Read-only stored weekly-report lookup arguments."""

    sku_code: str = Field(min_length=1)
    week_id: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_identifier(self) -> ReportToolArguments:
        self.sku_code = self.sku_code.strip()
        if not self.sku_code:
            raise ValueError("sku_code must not be blank")
        return self


class ToolWarning(AgentSchema):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ToolError(AgentSchema):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ToolExecutionMetadata(AgentSchema):
    """Compact persisted/streamed execution facts, never raw retrieval payloads."""

    duration_ms: int | None = Field(default=None, ge=0)
    result_count: int | None = Field(default=None, ge=0)
    call_id: str | None = Field(default=None, min_length=1)


ToolArgumentsT = TypeVar("ToolArgumentsT", bound=AgentSchema)
ToolPayloadT = TypeVar("ToolPayloadT")


class ToolResult(AgentSchema, Generic[ToolArgumentsT, ToolPayloadT]):
    """Shared, typed result envelope for every deterministic Agent tool."""

    status: ToolStatus
    tool_name: ToolName
    normalized_args: ToolArgumentsT
    warnings: list[ToolWarning] = Field(default_factory=list)
    execution: ToolExecutionMetadata = Field(default_factory=ToolExecutionMetadata)
    payload: ToolPayloadT | None = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def validate_status_shape(self) -> ToolResult[ToolArgumentsT, ToolPayloadT]:
        if self.status is ToolStatus.ERROR:
            if self.error is None:
                raise ValueError("error status requires an error object")
            if self.payload is not None:
                raise ValueError("error status must not include a payload")
        elif self.error is not None:
            raise ValueError("only error status may include an error object")
        return self


class WeeklyReportPayload(AgentSchema):
    """Content and identifiers read verbatim from an existing weekly report."""

    report_id: UUID
    sku_code: str = Field(min_length=1)
    week_id: int = Field(ge=1)
    report_md: str | None = None
    summary: str | None = None
    generated_at: datetime


ReportToolResult = ToolResult[ReportToolArguments, WeeklyReportPayload]


class SkuSampleCount(AgentSchema):
    sku_code: str
    review_count: int = Field(ge=0)
    mention_count: int = Field(ge=0)


class ReviewCountPayload(AgentSchema):
    operation: Literal["review_count"] = "review_count"
    review_count: int = Field(ge=0)
    mention_count: int = Field(ge=0)
    by_sku: list[SkuSampleCount]


class SentimentBucket(AgentSchema):
    sentiment: Sentiment
    mention_count: int = Field(ge=0)
    proportion: float = Field(ge=0, le=1)


class SentimentDistributionPayload(AgentSchema):
    operation: Literal["sentiment_distribution"] = "sentiment_distribution"
    mention_count: int = Field(ge=0)
    distribution: list[SentimentBucket]


class AspectBucket(AgentSchema):
    aspect_label: str
    mention_count: int = Field(ge=0)
    proportion: float = Field(ge=0, le=1)
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)


class AspectDistributionPayload(AgentSchema):
    operation: Literal["aspect_distribution"] = "aspect_distribution"
    mention_count: int = Field(ge=0)
    distribution: list[AspectBucket]


class TrendPoint(AgentSchema):
    week_id: int
    review_count: int = Field(ge=0)
    mention_count: int = Field(ge=0)
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    positive_rate: float = Field(ge=0, le=1)
    negative_rate: float = Field(ge=0, le=1)
    neutral_rate: float = Field(ge=0, le=1)


class TrendPayload(AgentSchema):
    operation: Literal["trend", "aspect_trend"]
    aspect_label: str | None = None
    points: list[TrendPoint]


class SkuComparisonMetrics(AgentSchema):
    sku_code: str
    review_count: int = Field(ge=0)
    mention_count: int = Field(ge=0)
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    positive_rate: float = Field(ge=0, le=1)
    negative_rate: float = Field(ge=0, le=1)
    neutral_rate: float = Field(ge=0, le=1)
    sentiment_score: float = Field(ge=-1, le=1)


class SkuComparisonPayload(AgentSchema):
    operation: Literal["compare_skus"] = "compare_skus"
    capacity_tier: str
    comparison_metric: ComparisonMetric | None = None
    skus: list[SkuComparisonMetrics]


AnalyticsPayload = (
    ReviewCountPayload
    | SentimentDistributionPayload
    | AspectDistributionPayload
    | TrendPayload
    | SkuComparisonPayload
)

AnalyticsToolResult = ToolResult[AnalyticsToolArguments, AnalyticsPayload]


class ExpandedSourceMetadata(AgentSchema):
    """Stable metadata required to retrieve or render a larger source review."""

    document_id: UUID
    sku_code: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    published_at: datetime | None = None
    source_url: str | None = None
    title: str | None = None
    rating: int | None = None
    review_text: str | None = None


class RetrievedEvidence(AgentSchema):
    """Internal RAG evidence after Milvus hit hydration from PostgreSQL."""

    mention_id: UUID
    document_id: UUID
    sku_code: str = Field(min_length=1)
    aspect_label: str = Field(min_length=1)
    sentiment: Sentiment
    week_id: int = Field(ge=1)
    mention_text: str = Field(min_length=1)
    context_window: str | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    similarity_score: float | None = None
    source: ExpandedSourceMetadata

    @model_validator(mode="after")
    def validate_source_provenance(self) -> RetrievedEvidence:
        if self.document_id != self.source.document_id:
            raise ValueError("document_id must match source.document_id")
        return self


class RagRetrievalPayload(AgentSchema):
    query: str
    retrieved_count: int = Field(ge=0)
    evidence: list[RetrievedEvidence]


RagToolResult = ToolResult[RagToolArguments, RagRetrievalPayload]


class AnswerCitation(AgentSchema):
    """Evidence explicitly used in the final answer, not every retrieved hit."""

    mention_id: UUID
    document_id: UUID
    evidence_preview: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    aspect_label: str = Field(min_length=1)
    sentiment: Sentiment
    week_id: int = Field(ge=1)
    source: ExpandedSourceMetadata

    @model_validator(mode="after")
    def validate_source_provenance(self) -> AnswerCitation:
        if self.document_id != self.source.document_id:
            raise ValueError("document_id must match source.document_id")
        if self.sku_code != self.source.sku_code:
            raise ValueError("sku_code must match source.sku_code")
        return self


class ConversationMessage(AgentSchema):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class AgentStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ABSTAINED = "abstained"
    ERROR = "error"


class ToolCallTrace(AgentSchema):
    """User-visible execution facts only; never model reasoning or scratchpad."""

    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] | str | None = None
    normalized_arguments: dict[str, Any] | None = None
    executed: bool
    status: ToolStatus
    duration_ms: int | None = Field(default=None, ge=0)
    result_count: int | None = Field(default=None, ge=0)
    warnings: list[ToolWarning] = Field(default_factory=list)
    error: ToolError | None = None


class ToolCallLimitEvent(AgentSchema):
    attempted_call_id: str = Field(min_length=1)
    attempted_tool_name: str = Field(min_length=1)
    maximum: int = Field(ge=1)


class AgentExecutionMetadata(AgentSchema):
    model_round_count: int = Field(ge=0)
    attempted_tool_call_count: int = Field(ge=0)
    executed_tool_call_count: int = Field(ge=0)
    maximum_tool_calls: int = Field(ge=1)
    limit_event: ToolCallLimitEvent | None = None


class AgentRunResult(AgentSchema):
    status: AgentStatus
    final_answer: str = Field(min_length=1)
    error: ToolError | None = None
    citations: list[AnswerCitation] = Field(default_factory=list)
    warnings: list[ToolWarning] = Field(default_factory=list)
    tool_trace: list[ToolCallTrace] = Field(default_factory=list)
    execution: AgentExecutionMetadata


class ConversationTurnResult(AgentSchema):
    session_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    agent_result: AgentRunResult


class ToolStartedEvent(AgentSchema):
    event_type: Literal["tool_started"] = "tool_started"
    call_id: str = Field(min_length=1)
    tool_name: ToolName


class ToolCompletedEvent(AgentSchema):
    event_type: Literal["tool_completed"] = "tool_completed"
    call_id: str = Field(min_length=1)
    tool_name: ToolName
    status: ToolStatus
    warnings: list[ToolWarning] = Field(default_factory=list)
    execution: ToolExecutionMetadata = Field(default_factory=ToolExecutionMetadata)


class AnswerDeltaEvent(AgentSchema):
    event_type: Literal["answer_delta"] = "answer_delta"
    delta: str = Field(min_length=1)


class CitationEvent(AgentSchema):
    event_type: Literal["citation"] = "citation"
    citation: AnswerCitation


class DoneEvent(AgentSchema):
    event_type: Literal["done"] = "done"
    session_id: UUID | None = None
    user_message_id: UUID | None = None
    assistant_message_id: UUID | None = None
    status: AgentStatus | None = None


class ErrorEvent(AgentSchema):
    event_type: Literal["error"] = "error"
    error: ToolError


StreamingEvent = Annotated[
    ToolStartedEvent
    | ToolCompletedEvent
    | AnswerDeltaEvent
    | CitationEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="event_type"),
]


streaming_event_adapter = TypeAdapter(StreamingEvent)


class ReportStartedEvent(AgentSchema):
    event_type: Literal["report_started"] = "report_started"
    sku_code: str = Field(min_length=1)
    week_id: int = Field(ge=1)


class ReportStageStartedEvent(AgentSchema):
    event_type: Literal["stage_started"] = "stage_started"
    stage: Literal[
        "collecting_analytics",
        "retrieving_evidence",
        "synthesizing",
        "validating",
        "persisting",
    ]


class ReportStageCompletedEvent(ReportStageStartedEvent):
    event_type: Literal["stage_completed"] = "stage_completed"
    warnings: list[str] = Field(default_factory=list)


class ReportDeltaEvent(AgentSchema):
    event_type: Literal["report_delta"] = "report_delta"
    delta: str = Field(min_length=1)


class ReportCompletedEvent(AgentSchema):
    event_type: Literal["report_completed"] = "report_completed"
    report: WeeklyReportPayload


class ReportErrorEvent(AgentSchema):
    event_type: Literal["error"] = "error"
    error: ToolError


ReportStreamingEvent = Annotated[
    ReportStartedEvent
    | ReportStageStartedEvent
    | ReportStageCompletedEvent
    | ReportDeltaEvent
    | ReportCompletedEvent
    | ReportErrorEvent,
    Field(discriminator="event_type"),
]


report_streaming_event_adapter = TypeAdapter(ReportStreamingEvent)
