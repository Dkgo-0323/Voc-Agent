from backend.app.agent.request_scope import constrain_arguments, resolve_scope
from backend.app.agent.schemas import ConversationMessage


def test_mixed_request_has_independent_requirements():
    scope = resolve_scope("EcoFlow Delta 2怎么样，有多少评论，续航呢？", [])
    assert scope.data_request
    assert scope.tools == {"tool_sql", "tool_rag"}
    args = constrain_arguments(
        scope,
        "tool_rag",
        {
            "sku_codes": [],
            "week_range": {"start_week_id": 202313, "end_week_id": 202313},
        },
    )
    assert args == {"sku_codes": ["ecoflow-delta2"]}


def test_followup_uses_latest_user_product_not_assistant_claim():
    history = [
        ConversationMessage(role="user", content="Delta 2怎么样"),
        ConversationMessage(role="assistant", content="Jackery 300"),
        ConversationMessage(role="user", content="换成Jackery 1000"),
    ]
    scope = resolve_scope("它有多少评论？", history)
    assert scope.skus == ("jackery-explorer-1000",)
    assert resolve_scope("EcoFlow Delta 2怎么样", history).skus == ("ecoflow-delta2",)


def test_explicit_dates_and_comparison_are_preserved():
    scope = resolve_scope("比较 Delta 2 和 Jackery 1000 在2023年第13周的反馈", [])
    args = {"week_range": {"start_week_id": 202313, "end_week_id": 202313}}
    result = constrain_arguments(scope, "tool_sql", args)
    assert result["week_range"] == args["week_range"]
    assert len(result["sku_codes"]) == 2
    assert "sku_codes" not in args


def test_examples_do_not_force_data_queries():
    assert not resolve_scope("举一个关于Delta 2的提问示例", []).data_request
    assert not resolve_scope("你好", []).data_request


def test_report_schema_is_not_rewritten():
    scope = resolve_scope("读取Delta 2的2023年周报", [])
    args = {"sku_code": "ecoflow-delta2", "week_id": 202313}
    assert constrain_arguments(scope, "tool_report", args) == args


def test_unrequested_sentiment_does_not_hide_negative_feedback():
    scope = resolve_scope("Delta 2续航怎么样？", [])
    assert "sentiment" not in constrain_arguments(
        scope, "tool_rag", {"sentiment": "positive"}
    )
    scope = resolve_scope("Delta 2负面反馈如何？", [])
    assert (
        constrain_arguments(scope, "tool_rag", {"sentiment": "negative"})["sentiment"]
        == "negative"
    )
