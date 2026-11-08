"""Mutation tests: the business evaluator must reject plausible false passes."""

from copy import deepcopy

import pytest

from shared.eval.business_questions import HOLDOUT, SCENARIOS
from shared.eval.conversation_e2e import Question, assess, parse_sse


def receipt():
    events = [
        {"event_type": "answer_delta", "delta": "EcoFlow Delta 2 有 42 条评论。"},
        {
            "event_type": "done",
            "status": "success",
            "session_id": "s",
            "assistant_message_id": "a",
        },
    ]
    persisted = {
        "id": "a",
        "session_id": "s",
        "prompt": "有多少评论？",
        "content": events[0]["delta"],
        "tool_calls": {
            "calls": [
                {
                    "call_id": "c",
                    "tool_name": "tool_sql",
                    "executed": True,
                    "normalized_arguments": {
                        "operation": "review_count",
                        "sku_codes": ["ecoflow-delta2"],
                    },
                }
            ]
        },
        "tool_results": {
            "agent_status": "success",
            "results": [{"call_id": "c", "status": "success"}],
        },
        "cited_ids": {"mention_ids": []},
    }
    return events, persisted


Q = Question(
    "count",
    "有多少评论？",
    ("tool_sql",),
    "ecoflow-delta2",
    count=True,
    operations=("review_count",),
)


def test_real_receipt_and_independent_count_required():
    events, persisted = receipt()
    assert assess(Q, events, persisted=persisted, expected_count=42) == []
    assert "missing_persisted_receipt" in assess(Q, events, expected_count=42)
    assert "missing_count_oracle" in assess(Q, events, persisted=persisted)
    assert "count_oracle_mismatch" in assess(
        Q, events, persisted=persisted, expected_count=43
    )


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("failed_tool", "missing_successful_tool:tool_sql"),
        ("wrong_sku", "wrong_sku_scope"),
        ("extra_sku", "wrong_sku_scope"),
        ("invented_week", "unrequested_week_filter"),
        ("wrong_operation", "missing_operation:review_count"),
        ("unexecuted", "missing_data_query"),
        ("wrong_session", "persisted_turn_mismatch"),
        ("wrong_answer", "persisted_answer_mismatch"),
        ("filtered", "unexpected_count_filter"),
        ("wrong_status", "persisted_status_mismatch"),
    ],
)
def test_reject_false_pass(mutation, expected):
    events, persisted = receipt()
    call = persisted["tool_calls"]["calls"][0]
    if mutation == "failed_tool":
        persisted["tool_results"]["results"][0]["status"] = "error"
    elif mutation == "wrong_sku":
        call["normalized_arguments"]["sku_codes"] = ["jackery-explorer-1000"]
    elif mutation == "extra_sku":
        call["normalized_arguments"]["sku_codes"].append("jackery-explorer-1000")
    elif mutation == "invented_week":
        call["normalized_arguments"]["week_range"] = {
            "start_week_id": 202313,
            "end_week_id": 202313,
        }
    elif mutation == "wrong_operation":
        call["normalized_arguments"]["operation"] = "aspect_distribution"
    elif mutation == "unexecuted":
        call["executed"] = False
    elif mutation == "wrong_session":
        persisted["session_id"] = "other"
    elif mutation == "wrong_answer":
        persisted["content"] = "different"
    elif mutation == "filtered":
        call["normalized_arguments"]["sentiment"] = "negative"
    elif mutation == "wrong_status":
        persisted["tool_results"]["agent_status"] = "error"
    assert expected in assess(Q, events, persisted=persisted, expected_count=42)


def test_http_200_with_error_is_not_success():
    events = parse_sse(
        'event: error\r\ndata: {"event_type":"error","error":{"code":"agent_controlled_error"}}\r\n\r\n'
    )
    failures = assess(Q, events)
    assert "api_error:agent_controlled_error" in failures
    assert "empty_answer" in failures


def test_reject_duplicate_or_nonterminal_done():
    events, persisted = receipt()
    for broken in (events + [deepcopy(events[-1])], events + [events[0]], events[:-1]):
        assert "invalid_terminal_sequence" in assess(
            Q, broken, persisted=persisted, expected_count=42
        )


def test_citations_cannot_be_assumed_from_successful_retrieval():
    events, persisted = receipt()
    q = Question("runtime", Q.prompt, citation=True)
    assert "missing_citation" in assess(q, events, persisted=persisted)
    persisted["cited_ids"]["mention_ids"] = ["unreturned"]
    assert "citation_receipt_mismatch" in assess(q, events, persisted=persisted)


def test_dataset_is_diverse_and_holdout_is_separate():
    assert len(SCENARIOS) >= 20
    assert sum(len(s.turns) for s in SCENARIOS) > len(SCENARIOS)
    assert {s.id for s in SCENARIOS}.isdisjoint(s.id for s in HOLDOUT)
    assert len({q.prompt for s in SCENARIOS for q in s.turns}) == sum(
        len(s.turns) for s in SCENARIOS
    )


def test_bad_sse_rejected():
    with pytest.raises(ValueError):
        parse_sse('data: {"unexpected":"object"}\n\n')


def test_warning_sample_size_does_not_rescue_wrong_count():
    events, persisted = receipt()
    text = "共有 999 条评论。\nData notes:\n42 matching reviews"
    events[0]["delta"] = persisted["content"] = text
    assert "count_oracle_mismatch" in assess(
        Q, events, persisted=persisted, expected_count=42
    )
