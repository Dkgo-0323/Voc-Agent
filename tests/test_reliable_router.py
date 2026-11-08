from types import SimpleNamespace

import pytest

from backend.app.agent.evidence_integrity import (
    complete_context,
    sentiment_label_conflict,
    source_model_conflict,
)
from backend.app.agent.reliable import (
    ReliableVocRouter,
    evidence_quote,
    render_analytics,
)
from backend.app.agent.router import ToolBinding
from backend.app.agent.schemas import (
    AgentStatus,
    AnalyticsToolArguments,
    AspectDistributionPayload,
    RagToolArguments,
    ReviewCountPayload,
    SkuSampleCount,
    ToolName,
    ToolResult,
    ToolStatus,
    TrendPayload,
)


class UnavailableModel:
    async def complete(self, **kwargs):
        raise TimeoutError("provider unavailable")


def router(sql=None, rag=None):
    bindings = []
    if sql:
        bindings.append(
            ToolBinding(ToolName.SQL, "statistics", AnalyticsToolArguments, sql)
        )
    if rag:
        bindings.append(ToolBinding(ToolName.RAG, "evidence", RagToolArguments, rag))
    return ReliableVocRouter(UnavailableModel(), bindings, system_policy="")


def count_result(args):
    return ToolResult(
        status=ToolStatus.SUCCESS,
        tool_name=ToolName.SQL,
        normalized_args=args,
        payload=ReviewCountPayload(
            review_count=7,
            mention_count=13,
            by_sku=[
                SkuSampleCount(
                    sku_code="ecoflow-delta2", review_count=7, mention_count=13
                )
            ],
        ),
    )


@pytest.mark.asyncio
async def test_statistics_do_not_depend_on_a_working_language_model():
    calls, events = [], []

    async def sql(args):
        calls.append(args)
        return count_result(args)

    async def sink(event):
        events.append(event.event_type)

    result = await router(sql).run(
        recent_messages=[],
        current_user_message="EcoFlow Delta 2有多少评论？",
        event_sink=sink,
    )
    assert result.status is AgentStatus.SUCCESS
    assert "7 条评论，13 次方面提及" in result.final_answer
    assert "不是平台总评论量" in result.final_answer
    assert calls[0].week_range is None
    assert events == ["tool_started", "tool_completed"]


@pytest.mark.asyncio
async def test_query_failure_is_a_recoverable_answer_and_next_turn_still_works():
    attempts = 0

    async def sql(args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("internal connection details")
        return count_result(args)

    agent = router(sql)
    failed = await agent.run(
        recent_messages=[], current_user_message="Delta 2有多少评论？"
    )
    recovered = await agent.run(
        recent_messages=[], current_user_message="Delta 2有多少评论？"
    )
    assert failed.status is AgentStatus.PARTIAL
    assert failed.error is None
    assert "internal" not in failed.final_answer
    assert recovered.status is AgentStatus.SUCCESS


@pytest.mark.asyncio
async def test_missing_evidence_and_future_week_are_not_fabricated():
    seen = []

    async def rag(args):
        seen.append(args)
        return ToolResult(
            status=ToolStatus.EMPTY, tool_name=ToolName.RAG, normalized_args=args
        )

    result = await router(rag=rag).run(
        recent_messages=[], current_user_message="Delta 2在2099年第1周有什么用户反馈？"
    )
    assert result.status is AgentStatus.ABSTAINED
    assert seen[0].week_range.start_week_id == 209901
    assert not result.citations
    assert "无法据此下结论" in result.final_answer


@pytest.mark.asyncio
async def test_overly_precise_runtime_request_is_retrieved_but_not_guessed():
    seen = []

    async def rag(args):
        seen.append(args)
        return ToolResult(
            status=ToolStatus.EMPTY, tool_name=ToolName.RAG, normalized_args=args
        )

    result = await router(rag=rag).run(
        recent_messages=[],
        current_user_message="EcoFlow Delta 2带任何冰箱都能精确运行几小时？根据用户评论回答。",
    )
    assert len(seen) == 1
    assert "不能换算" in result.final_answer
    assert result.status is AgentStatus.ABSTAINED


@pytest.mark.asyncio
async def test_general_provider_failure_still_returns_a_normal_answer():
    result = await router().run(
        recent_messages=[], current_user_message="请解释一下用户体验分析的意义"
    )
    assert result.status is AgentStatus.ABSTAINED
    assert result.error is None
    assert result.execution.model_round_count >= 1


def test_iso_weeks_and_mention_denominators_are_rendered_from_values():
    payload = TrendPayload(
        operation="trend",
        points=[
            dict(
                week_id=202248,
                review_count=1,
                mention_count=3,
                positive_count=2,
                negative_count=1,
                neutral_count=0,
                positive_rate=2 / 3,
                negative_rate=1 / 3,
                neutral_rate=0,
            )
        ],
    )
    text = render_analytics(payload)
    assert "2022 年第 48 周（2022-11-28 至 2022-12-04）" in text
    assert "1 条评论、3 次提及" in text
    assert "33.33%" in text


def test_ambiguous_model_is_excluded_and_numeric_context_is_not_cut():
    assert source_model_conflict("ecoflow-delta2", "I used the Delta Max 2.")
    assert not source_model_conflict("ecoflow-delta2", "The Delta 2 worked well.")
    raw = "The fan was loud. " + " " * 381 + "I reduced it to 700 watts."
    excerpt = complete_context(raw, "fan was loud")
    assert not excerpt.endswith("7")
    assert "700" in excerpt


def test_runtime_quote_keeps_load_and_does_not_treat_charging_as_endurance():
    item = SimpleNamespace(
        mention_text="fast charging",
        source=SimpleNamespace(
            review_text="It charges for 4 hours.<br>I ran a desktop and monitor for 2.5 hours and it dropped to 79%."
        ),
    )
    quote = evidence_quote(item, runtime=True)
    assert "desktop and monitor" in quote
    assert "2.5 hours" in quote
    assert "charges for 4 hours" not in quote


def test_explicit_criticism_cannot_be_displayed_as_verified_praise():
    assert sentiment_label_conflict("positive", "The app also needs some refinement")
    assert not sentiment_label_conflict("positive", "I had no trouble connecting")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,sentiment",
    [
        ("Delta 2用户最喜欢什么？引用两条原话。", "positive"),
        ("Delta 2差评主要集中在哪些方面？给数量和评论例子。", "negative"),
    ],
)
async def test_aspect_questions_use_complete_distribution_and_requested_sentiment(
    question, sentiment
):
    seen = []

    async def sql(args):
        seen.append(args)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            tool_name=ToolName.SQL,
            normalized_args=args,
            payload=AspectDistributionPayload(mention_count=0, distribution=[]),
        )

    async def rag(args):
        seen.append(args)
        return ToolResult(
            status=ToolStatus.EMPTY, tool_name=ToolName.RAG, normalized_args=args
        )

    result = await router(sql, rag).run(
        recent_messages=[], current_user_message=question
    )
    assert seen[0].operation.value == "aspect_distribution"
    assert seen[0].aspect_label is None
    assert seen[1].sentiment.value == sentiment
    assert result.status is AgentStatus.PARTIAL
