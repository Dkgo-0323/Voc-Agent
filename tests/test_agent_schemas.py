from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.agent.schemas import (
    AnalyticsOperation,
    AnalyticsToolArguments,
    AnswerCitation,
    CitationEvent,
    ExpandedSourceMetadata,
    RagToolArguments,
    Sentiment,
    ToolError,
    ToolName,
    ToolResult,
    ToolStatus,
    streaming_event_adapter,
)


def test_analytics_arguments_accept_fixed_operation_and_structured_filters() -> None:
    arguments = AnalyticsToolArguments(
        operation=AnalyticsOperation.SENTIMENT_DISTRIBUTION,
        sku_codes=["ecoflow-delta2"],
        week_range={"start_week_id": 202601, "end_week_id": 202603},
        sentiment=Sentiment.NEGATIVE,
    )

    assert arguments.model_dump(mode="json") == {
        "operation": "sentiment_distribution",
        "sku_codes": ["ecoflow-delta2"],
        "week_range": {"start_week_id": 202601, "end_week_id": 202603},
        "aspect_label": None,
        "sentiment": "negative",
        "comparison_metric": None,
        "limit": 10,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "execute_sql"},
        {"operation": "compare_skus", "sku_codes": ["ecoflow-delta2"]},
        {"operation": "aspect_trend"},
        {
            "operation": "trend",
            "week_range": {"start_week_id": 202603, "end_week_id": 202602},
        },
    ],
)
def test_analytics_arguments_reject_unsupported_or_malformed_requests(payload: dict) -> None:
    with pytest.raises(ValidationError):
        AnalyticsToolArguments.model_validate(payload)


def test_rag_arguments_require_non_blank_query_and_distinct_skus() -> None:
    with pytest.raises(ValidationError, match="query must not be blank"):
        RagToolArguments(query="   ")
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        RagToolArguments(query="noise", sku_codes=["ecoflow-delta2", "ecoflow-delta2"])


def test_tool_result_enforces_structured_error_state() -> None:
    arguments = AnalyticsToolArguments(operation=AnalyticsOperation.REVIEW_COUNT)
    error_result = ToolResult[AnalyticsToolArguments, int](
        status=ToolStatus.ERROR,
        tool_name=ToolName.SQL,
        normalized_args=arguments,
        error=ToolError(code="database_unavailable", message="Please retry", retryable=True),
    )

    assert error_result.payload is None
    with pytest.raises(ValidationError, match="requires an error"):
        ToolResult[AnalyticsToolArguments, int](
            status=ToolStatus.ERROR,
            tool_name=ToolName.SQL,
            normalized_args=arguments,
        )


@pytest.mark.parametrize(
    "status",
    [ToolStatus.SUCCESS, ToolStatus.EMPTY, ToolStatus.NOT_FOUND, ToolStatus.PARTIAL],
)
def test_tool_result_accepts_every_required_non_error_state(status: ToolStatus) -> None:
    result = ToolResult[AnalyticsToolArguments, int](
        status=status,
        tool_name=ToolName.SQL,
        normalized_args=AnalyticsToolArguments(operation=AnalyticsOperation.REVIEW_COUNT),
    )

    assert result.status is status


def test_citations_preserve_mention_and_document_provenance() -> None:
    mention_id = uuid4()
    document_id = uuid4()
    source = ExpandedSourceMetadata(
        document_id=document_id,
        sku_code="ecoflow-delta2",
        platform="amazon",
    )
    citation = AnswerCitation(
        mention_id=mention_id,
        document_id=document_id,
        evidence_preview="The fan is louder than expected.",
        sku_code="ecoflow-delta2",
        aspect_label="noise_level",
        sentiment=Sentiment.NEGATIVE,
        week_id=202603,
        source=source,
    )

    assert citation.mention_id == mention_id
    assert citation.source.document_id == document_id


def test_streaming_event_union_is_discriminated_and_serializable() -> None:
    event = streaming_event_adapter.validate_python(
        {"event_type": "tool_started", "call_id": "call-1", "tool_name": "tool_rag"}
    )

    assert event.event_type == "tool_started"
    assert streaming_event_adapter.dump_python(event, mode="json") == {
        "event_type": "tool_started",
        "call_id": "call-1",
        "tool_name": "tool_rag",
    }
    with pytest.raises(ValidationError):
        streaming_event_adapter.validate_python({"event_type": "reasoning"})


def test_citation_event_contains_only_final_citation_shape() -> None:
    document_id = uuid4()
    event = CitationEvent(
        citation=AnswerCitation(
            mention_id=uuid4(),
            document_id=document_id,
            evidence_preview="charges reliably",
            sku_code="ecoflow-delta2",
            aspect_label="charging",
            sentiment=Sentiment.POSITIVE,
            week_id=202603,
            source=ExpandedSourceMetadata(
                document_id=document_id,
                sku_code="ecoflow-delta2",
                platform="reddit",
            ),
        )
    )

    assert event.event_type == "citation"
