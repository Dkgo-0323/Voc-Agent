"""Exact-run audits must not accidentally pass using historical/failed turns."""

import json
import subprocess
import sys
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts.verify_phase14_agent_traces import EXPECTATIONS
from shared.acceptance.planning import build_plan
from shared.acceptance.receipts import audit_turns, validate_receipt


def fixture():
    run_id, session_id, mention_id = (str(uuid4()) for _ in range(3))
    turns, messages = [], []
    for expected in EXPECTATIONS:
        user_id, assistant_id = str(uuid4()), str(uuid4())
        turns.append(
            dict(
                session_id=session_id,
                user_message_id=user_id,
                assistant_message_id=assistant_id,
            )
        )
        messages.extend(
            [
                SimpleNamespace(
                    id=user_id,
                    session_id=session_id,
                    role="user",
                    content=expected.prompt,
                ),
                SimpleNamespace(
                    id=assistant_id,
                    session_id=session_id,
                    role="assistant",
                    tool_calls={
                        "calls": [
                            dict(
                                tool_name=tool,
                                executed=True,
                                normalized_arguments={
                                    "week_range": {
                                        "start_week_id": 202403,
                                        "end_week_id": 202403,
                                    }
                                },
                            )
                            for tool in expected.tools
                        ]
                    },
                    tool_results={"agent_status": expected.status},
                    cited_ids={
                        "mention_ids": [mention_id] if expected.require_citation else []
                    },
                ),
            ]
        )
    receipt = dict(schema_version=1, run_id=run_id, turns=turns)
    return receipt, messages, dict(run_id=run_id, allowed_mention_ids={mention_id})


def test_exact_turns_pass_without_exposing_message_content():
    receipt, messages, kwargs = fixture()
    report = audit_turns(receipt, messages, EXPECTATIONS, **kwargs)
    assert report["verified_turns"] == 5
    assert "prompt" not in json.dumps(report)
    assert len(report["traceable_citation_ids"]) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_run",
        "wrong_session",
        "old_message",
        "wrong_prompt",
        "extra_turn",
        "missing_turn",
        "wrong_role",
        "unexecuted_tool",
        "failed_turn",
        "partial_turn",
        "wrong_followup_week",
        "foreign_citation",
        "missing_citation",
        "duplicate_citation",
        "cited_abstention",
        "duplicate_receipt_id",
        "split_session",
    ],
)
def test_failed_or_unrelated_evidence_is_rejected(mutation):
    receipt, messages, kwargs = fixture()
    if mutation == "wrong_run":
        receipt["run_id"] = str(uuid4())
    elif mutation == "wrong_session":
        messages[1].session_id = str(uuid4())
    elif mutation == "old_message":
        messages[1].id = str(uuid4())
    elif mutation == "wrong_prompt":
        messages[0].content = "historical question"
    elif mutation == "extra_turn":
        messages.extend(deepcopy(messages[:2]))
    elif mutation == "missing_turn":
        messages.pop()
    elif mutation == "wrong_role":
        messages[1].role = "user"
    elif mutation == "unexecuted_tool":
        messages[1].tool_calls["calls"][0]["executed"] = False
    elif mutation == "failed_turn":
        messages[1].tool_results["agent_status"] = "error"
    elif mutation == "partial_turn":
        messages[1].tool_results["agent_status"] = "partial"
    elif mutation == "wrong_followup_week":
        for call in messages[7].tool_calls["calls"]:
            call["normalized_arguments"]["week_range"]["end_week_id"] = 202404
    elif mutation == "foreign_citation":
        messages[3].cited_ids["mention_ids"] = [str(uuid4())]
    elif mutation == "missing_citation":
        messages[3].cited_ids["mention_ids"] = []
    elif mutation == "duplicate_citation":
        messages[3].cited_ids["mention_ids"] *= 2
    elif mutation == "cited_abstention":
        messages[9].cited_ids["mention_ids"] = list(kwargs["allowed_mention_ids"])
    elif mutation == "duplicate_receipt_id":
        receipt["turns"][1]["user_message_id"] = receipt["turns"][0]["user_message_id"]
    elif mutation == "split_session":
        receipt["turns"][1]["session_id"] = str(uuid4())
    with pytest.raises(ValueError):
        audit_turns(receipt, messages, EXPECTATIONS, **kwargs)


@pytest.mark.parametrize("receipt", [[], {}, {"schema_version": 8}])
def test_malformed_receipt_never_reaches_database(receipt):
    with pytest.raises(ValueError):
        validate_receipt(receipt, run_id=str(uuid4()))


def test_inventory_is_not_execution_or_budget_approval():
    plan = build_plan(documents=30)
    assert plan["proposed_request_upper_bound"] == {
        "chat": 72,
        "embedding": 24,
        "total": 96,
    }
    assert plan["live_authorized"] is False
    assert plan["enforced_by_runtime"] is False
    assert plan["models"]["chat"] is None and plan["cost_cny"] is None


@pytest.mark.parametrize("count", [0, -1, 31])
def test_excessive_source_scope_rejected(count):
    with pytest.raises(ValueError):
        build_plan(documents=count)


def test_planner_cli_works_outside_checkout_without_loading_settings(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/plan_business_acceptance.py"
    # Loading this file would fail Settings validation. It must remain irrelevant.
    (tmp_path / ".env").write_text("APP_ENV=production\nEMBEDDING_DIMENSIONS=-1\n")
    code = (
        "import runpy,sys,socket; "
        "socket.socket.connect=lambda *a: (_ for _ in ()).throw(AssertionError('network')); "
        f"sys.argv=[{str(script)!r}, '--documents', '2']; "
        f"runpy.run_path({str(script)!r},run_name='__main__')"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["documents"] == 2
    assert result.stderr == ""


@pytest.mark.asyncio
async def test_verifier_queries_only_the_receipt_session_and_closes_database(
    monkeypatch,
):
    from backend.app.core import database
    from scripts.seed_phase14_demo_data import _id
    from scripts.verify_phase14_agent_traces import verify_agent_traces

    receipt, messages, kwargs = fixture()
    mention = str(_id("mention", 0))
    for message in messages[1::2]:
        if message.cited_ids["mention_ids"]:
            message.cited_ids["mention_ids"] = [mention]
    statements, lifecycle = [], []

    class Session:
        async def scalars(self, statement):
            statements.append(statement)
            return SimpleNamespace(all=lambda: messages)

    @asynccontextmanager
    async def context():
        yield Session()

    async def init():
        lifecycle.append("init")

    async def close():
        lifecycle.append("close")

    monkeypatch.setattr(database, "get_db_context", context)
    monkeypatch.setattr(database, "init_db", init)
    monkeypatch.setattr(database, "close_db", close)
    result = await verify_agent_traces(receipt, run_id=kwargs["run_id"])
    assert result["verified_turns"] == 5
    assert len(statements) == 1
    assert (
        str(statements[0].compile().params["session_id_1"])
        == receipt["turns"][0]["session_id"]
    )
    assert lifecycle == ["init", "close"]
