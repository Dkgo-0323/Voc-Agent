"""Real SDK and API lifespan across stages, with fake storage and provider wire."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from openai import APIConnectionError

from backend.app import main
from scripts import seed_phase14_demo_data as demo
from shared.acceptance.browser import browser_exercise
from shared.acceptance.runtime import acceptance_adapters
from shared.acceptance.server import http_exercise
from shared.acceptance.transport import AcceptanceStopped, ProviderPolicy
from shared.acceptance.workflow import RunRecord, run_business_acceptance


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "extra_message", "citation", "stale_report", "query", "wrong_sku", "wrong_week"])
async def test_database_audit_in_workflow(monkeypatch, failure):
    from shared.acceptance.audit import database_audit
    from shared.acceptance.receipts import TurnExpectation
    from shared.acceptance.reports import content_hash

    close = storage(monkeypatch)
    wire = Wire()
    record = RunRecord(str(uuid4()))
    ask, reports = receipts(record.run_id)
    if failure in {"wrong_sku", "wrong_week"}:
        for report in reports["reports"]:
            report["sku_code" if failure == "wrong_sku" else "week_id"] = (
                "jackery-explorer-1000" if failure == "wrong_sku" else 202404
            )
    last = reports["reports"][-1]
    last["content_sha256"] = content_hash("report", "summary")
    expected = tuple(TurnExpectation(f"prompt {i}", frozenset(), status="success") for i in range(5))
    messages = []
    for turn, expectation in zip(ask["turns"], expected, strict=True):
        for role, key in (("user", "user_message_id"), ("assistant", "assistant_message_id")):
            messages.append(SimpleNamespace(
                id=turn[key], session_id=turn["session_id"], role=role,
                content=expectation.prompt, tool_calls={},
                tool_results={"agent_status": "success"}, cited_ids={},
            ))
    if failure == "extra_message":
        messages.append(messages[-1])
    if failure == "citation":
        messages[1].cited_ids = {"mention_ids": [str(uuid4())]}
    stored = SimpleNamespace(**last, report_md="report", summary="summary")
    if failure == "stale_report":
        stored.generated_at = reports["reports"][0]["generated_at"]
    statements, exits = [], []

    async def scalars(statement):
        statements.append(statement)
        if failure == "query":
            raise RuntimeError("database unavailable")
        return SimpleNamespace(all=lambda: messages)

    session = SimpleNamespace(scalars=scalars)

    @asynccontextmanager
    async def context():
        assert close.await_count == 0
        try:
            yield session
        finally:
            exits.append(True)

    report_read = AsyncMock(return_value=stored)
    monkeypatch.setattr("shared.acceptance.audit.ReportRepository.get_weekly_report", report_read)
    audit = database_audit(
        context, expectations=expected, allowed_mention_ids=set(),
        report_sku="ecoflow-delta2", report_week=202403,
    )

    async def noop(adapters):
        pass

    async def exercise(app, run_id):
        return ask, reports

    async def run():
        await run_business_acceptance(
            record, POLICY, api_key="offline", transport=wire,
            prepare=noop, seed=noop, exercise=exercise, audit=audit,
        )

    if failure:
        with pytest.raises(RuntimeError if failure == "query" else ValueError):
            await run()
        assert record.status == "failed" and record.provider["stopped"]
    else:
        await run()
        assert record.status == "completed"
    if failure in {"wrong_sku", "wrong_week"}:
        assert not exits and not statements
        report_read.assert_not_awaited()
        assert close.await_count == 1 and wire.closed
        assert record.stages[-1]["name"] == "audit"
        return
    assert exits == [True] and close.await_count == 1 and wire.closed
    assert record.provider["outbound_attempts"] == {"chat": 0, "embedding": 1}
    statement = statements[0]
    assert str(statement.compile().params["session_id_1"]) == ask["turns"][0]["session_id"]
    assert "ORDER BY chat_messages.created_at, chat_messages.id" in str(statement)
    assert report_read.await_count == (0 if failure in {"extra_message", "citation", "query"} else 1)

POLICY = ProviderPolicy("https://provider.invalid/v4", "chat-test", "embed-test")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "stale", "audit", "exit"])
async def test_child_http_receipts_and_audit_share_one_workflow(tmp_path, monkeypatch, failure):
    """Real child + HTTP + SDK; test-only route, synthetic receipts and storage."""
    close = storage(monkeypatch)
    wire, record = Wire(), RunRecord(str(uuid4()))
    ask, reports = receipts(record.run_id)
    apps, listeners = [], []
    original = main.create_app

    def factory(**kwargs):
        app = original(**kwargs)
        apps.append(app)

        @app.get("/test-child-receipts")
        async def endpoint():
            assert close.await_count == 0
            await app.state.acceptance_adapters.chat.complete(messages=[], tools=[])
            return {"ask": ask, "reports": reports}

        return app

    monkeypatch.setattr("shared.acceptance.workflow.create_app", factory)
    import uvicorn
    startup = uvicorn.Server.startup

    async def capture(self, sockets):
        await startup(self, sockets)
        listeners.extend(self.servers)

    monkeypatch.setattr(uvicorn.Server, "startup", capture)
    child = tmp_path / "http_child.py"
    child.write_text('''import json, os, pathlib, sys, urllib.request
url = os.environ["PHASE14_API_BASE_URL"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(url + "/test-child-receipts", timeout=5) as response:
    payload = json.load(response)
if sys.argv[1] == "exit":
    sys.exit(7)
assert payload["ask"]["run_id"] == os.environ["PHASE14_RUN_ID"]
if sys.argv[1] == "stale":
    payload["ask"]["run_id"] = "00000000-0000-0000-0000-000000000000"
root = pathlib.Path(os.environ["PHASE14_RECEIPT_DIR"])
for name, key in (("ask", "ask"), ("report", "reports")):
    (root / (name + "-receipt.json")).write_text(json.dumps(payload[key]))
''', encoding="utf-8")
    root = tmp_path / "receipts"
    root.mkdir()
    callback = browser_exercise(
        [sys.executable, str(child), str(failure)], cwd=tmp_path,
        environment={k: v for k, v in os.environ.items()
                     if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH"}},
        receipt_root=root, timeout=15,
    )
    audit = AsyncMock(side_effect=ValueError("audit mismatch") if failure == "audit" else None)
    noop = AsyncMock()
    kwargs = dict(api_key="offline", transport=wire, prepare=noop, seed=noop,
                  exercise=http_exercise(callback), audit=audit)
    if failure:
        with pytest.raises(RuntimeError if failure == "exit" else ValueError):
            await run_business_acceptance(record, POLICY, **kwargs)
        assert record.status == "failed" and record.provider["stopped"]
    else:
        await run_business_acceptance(record, POLICY, **kwargs)
        assert record.status == "completed" and not record.provider["stopped"]
        audit.assert_awaited_once_with(ask, reports, record.run_id)
    if failure in {"stale", "exit"}:
        audit.assert_not_awaited()
    assert len(apps) == 1 and close.await_count == 1 and wire.closed
    assert record.provider["outbound_attempts"] == {"chat": 1, "embedding": 1}
    assert listeners and all(not listener.is_serving() for listener in listeners)
    assert list(root.iterdir()) == []


@pytest.mark.asyncio
async def test_http_bridge_uses_workflow_app_and_shared_quota(monkeypatch):
    close = storage(monkeypatch)
    wire = Wire()
    record = RunRecord(str(uuid4()))
    apps = []
    original = main.create_app

    def factory(**kwargs):
        app = original(**kwargs)
        apps.append(app)

        @app.get("/test-shared-chat")
        async def chat():
            await app.state.acceptance_adapters.chat.complete(messages=[], tools=[])
            return {"calls": app.state.acceptance_adapters.guard.summary()["outbound_attempts"]}

        return app

    monkeypatch.setattr("shared.acceptance.workflow.create_app", factory)

    async def noop(adapters):
        pass

    async def browser(base_url, run_id):
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            response = await client.get(base_url + "/test-shared-chat")
        assert response.status_code == 200
        assert response.json()["calls"] == {"chat": 1, "embedding": 1}
        assert close.await_count == 0
        return receipts(run_id)

    async def audit(*args):
        assert close.await_count == 0

    await run_business_acceptance(
        record, POLICY, api_key="offline", transport=wire,
        prepare=noop, seed=noop, exercise=http_exercise(browser), audit=audit,
    )
    assert len(apps) == 1 and close.await_count == 1
    assert record.status == "completed" and wire.closed
    assert record.provider["outbound_attempts"] == {"chat": 1, "embedding": 1}


def receipts(run_id):
    session, report_id = str(uuid4()), str(uuid4())
    ask = {"schema_version": 1, "run_id": run_id, "turns": [
        {"session_id": session, "user_message_id": str(uuid4()),
         "assistant_message_id": str(uuid4())} for _ in range(5)
    ]}
    report = {"report_id": report_id, "sku_code": "ecoflow-delta2",
              "week_id": 202403, "content_sha256": "a" * 64}
    return ask, {"schema_version": 1, "run_id": run_id, "reports": [
        {**report, "generated_at": "2026-10-28T06:00:00Z"},
        {**report, "generated_at": "2026-10-28T06:01:00Z"},
    ]}


def storage(monkeypatch, *, close_failure=False):
    @asynccontextmanager
    async def context():
        yield object()

    monkeypatch.setattr(main, "init_db", AsyncMock())
    close = AsyncMock(side_effect=RuntimeError("private shutdown") if close_failure else None)
    monkeypatch.setattr(main, "close_db", close)
    monkeypatch.setattr(main, "get_db_context", context)
    monkeypatch.setattr(main.AspectRepository, "validate_locked_skus", AsyncMock())
    monkeypatch.setattr(main.MilvusRepository, "setup_collection", lambda self: None)
    return close


class Wire(httpx.AsyncBaseTransport):
    def __init__(self, *, bad_startup=False):
        self.calls = []
        self.closed = False
        self.bad_startup = bad_startup

    async def handle_async_request(self, request):
        payload = json.loads(request.content)
        self.calls.append(payload)
        if request.url.path.endswith("embeddings"):
            dimensions = 768 if self.bad_startup and len(self.calls) == 4 else 1024
            return httpx.Response(200, json={
                "data": [{"index": i, "embedding": [0.1] * dimensions,
                          "object": "embedding"} for i in range(len(payload["input"]))],
                "model": "embed-test", "object": "list",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            })
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0,
            "model": "chat-test", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": "answer"},
                "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        })

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    None, "prepare", "seed", "repeat_seed", "startup", "exercise", "audit",
    "receipt", "cancel", "swallowed", "shutdown", "quota",
])
async def test_shared_run_order_failure_receipts_and_cleanup(monkeypatch, failure):
    close = storage(monkeypatch, close_failure=failure == "shutdown")
    wire = Wire(bad_startup=failure == "startup")
    record = RunRecord(str(uuid4()))
    seen, shared = [], []

    async def prepare(adapters):
        shared.append(adapters)
        seen.append("prepare")
        await adapters.chat.complete(messages=[], tools=[])
        if failure == "prepare":
            raise RuntimeError("private review/key must not enter diagnostics")
        if failure == "swallowed":
            adapters.guard.stop()

    async def seed(adapters):
        assert adapters is shared[0]
        name = "repeat_seed" if "seed" in seen else "seed"
        seen.append(name)
        await adapters.embedder.embed(["private review"])
        if failure == name:
            raise RuntimeError("private database error")

    async def exercise(app, run_id):
        seen.append("exercise")
        assert app.state.acceptance_adapters is shared[0]
        assert len(wire.calls) == 4  # prepare + both seeds + startup dimension probe
        await app.state.acceptance_adapters.chat.complete(messages=[], tools=[])
        if failure == "exercise":
            raise RuntimeError("private browser error")
        if failure == "cancel":
            raise asyncio.CancelledError()
        if failure == "receipt":
            return receipts(str(uuid4()))
        return receipts(run_id)

    async def audit(ask, reports, run_id):
        seen.append("audit")
        assert ask["run_id"] == reports["run_id"] == run_id == record.run_id
        assert close.await_count == 0  # DB still alive for the exact-row audit
        if failure == "audit":
            raise ValueError("private persisted content mismatch")

    policy = ProviderPolicy(POLICY.base_url, POLICY.chat_model, POLICY.embedding_model,
                            embedding_requests=2) if failure == "quota" else POLICY
    kwargs = dict(api_key="offline-secret", transport=wire, prepare=prepare,
                  seed=seed, exercise=exercise, audit=audit)
    if failure is None:
        await run_business_acceptance(record, policy, **kwargs)
        assert record.status == "completed"
        assert seen == ["prepare", "seed", "repeat_seed", "exercise", "audit"]
        assert record.provider["outbound_attempts"] == {"chat": 2, "embedding": 3}
        assert record.provider["reported_tokens"] == {"prompt": 10, "completion": 6}
        assert not record.provider["stopped"]
        assert all(stage["status"] == "completed" for stage in record.stages)
    else:
        expected = {
            "receipt": ValueError, "audit": ValueError, "cancel": asyncio.CancelledError,
            "swallowed": AcceptanceStopped, "quota": APIConnectionError,
        }.get(failure, RuntimeError)
        with pytest.raises(expected):
            await run_business_acceptance(record, policy, **kwargs)
        assert record.status == "failed"
        assert record.provider["stopped"]
        count = len(wire.calls)
        with pytest.raises(APIConnectionError):
            await shared[0].chat.complete(messages=[], tools=[])
        assert len(wire.calls) == count
        assert "audit" not in seen or failure in {"audit", "shutdown"}
        assert any(stage["status"] == "failed" for stage in record.stages)
    assert wire.closed
    assert close.await_count == (0 if failure in {
        "prepare", "seed", "repeat_seed", "swallowed",
    } else 1)
    serialized = json.dumps(asdict(record))
    assert "private" not in serialized and "offline-secret" not in serialized
    assert record.provider["cost_cny"] is None
    assert record.provider["monetary_cap_enforced"] is False
    with pytest.raises(ValueError, match="reused"):
        await run_business_acceptance(record, policy, **kwargs)


@pytest.mark.asyncio
async def test_replanning_required_before_any_callback_or_wire():
    record = RunRecord(str(uuid4()))
    wire, callback = Wire(), AsyncMock()
    with pytest.raises(ValueError, match="Replan"):
        await run_business_acceptance(
            record, ProviderPolicy(POLICY.base_url, "chat", "embed", chat_requests=73),
            api_key="offline", transport=wire, prepare=callback, seed=callback,
            exercise=callback, audit=callback,
        )
    callback.assert_not_awaited()
    assert not wire.calls and record.status == "not_started"


@pytest.mark.asyncio
async def test_real_seed_twice_borrows_embedder_without_new_client(monkeypatch):
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(all=lambda: [
        (item.sku_code, uuid4()) for item in demo.DEMO_MENTIONS
    ])

    @asynccontextmanager
    async def context():
        yield session

    monkeypatch.setattr(demo, "init_db", AsyncMock())
    close = AsyncMock()
    monkeypatch.setattr(demo, "close_db", close)
    monkeypatch.setattr(demo, "get_db_context", context)
    records = []

    def upsert(self, batch):
        records.append(batch)
        return len(batch)

    def forbidden():
        raise AssertionError("Seed must borrow the run embedder")

    monkeypatch.setattr(demo, "Embedder", forbidden)
    monkeypatch.setattr(demo.MilvusRepository, "upsert_vectors", upsert)
    wire = Wire()
    async with acceptance_adapters(POLICY, api_key="offline", transport=wire) as adapters:
        await demo.seed_demo_data(embedder=adapters.embedder)
        await demo.seed_demo_data(embedder=adapters.embedder)
        await adapters.chat.complete(messages=[], tools=[])
        assert adapters.guard.summary()["outbound_attempts"] == {"chat": 1, "embedding": 2}
    assert len(records) == 2 and len(records[0]) == len(demo.DEMO_MENTIONS)
    assert [row.id for row in records[0]] == [row.id for row in records[1]]
    assert session.merge.await_count == len(demo.DEMO_MENTIONS) * 4
    assert close.await_count == 2 and wire.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["prepare", "seed", "startup", "exercise", "audit", "swallowed"])
async def test_workflow_deadline_stops_run_and_closes_resources(monkeypatch, blocked):
    close = storage(monkeypatch)
    wire, record = Wire(), RunRecord(str(uuid4()))
    entered, released = asyncio.Event(), asyncio.Event()
    adapters_seen = []

    async def block(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if blocked != "swallowed":
                raise
        finally:
            released.set()

    async def prepare(adapters):
        adapters_seen.append(adapters)
        if blocked in {"prepare", "swallowed"}:
            await block()

    async def seed(adapters):
        if blocked == "seed":
            await block()

    async def exercise(app, run_id):
        if blocked == "exercise":
            await block()
        return receipts(run_id)

    async def audit(*args):
        if blocked == "audit":
            await block()

    if blocked == "startup":
        monkeypatch.setattr(main.AspectRepository, "validate_locked_skus", block)
    task = asyncio.create_task(run_business_acceptance(
        record, POLICY, api_key="offline", transport=wire,
        prepare=prepare, seed=seed, exercise=exercise, audit=audit, timeout=1,
    ))
    await asyncio.wait_for(entered.wait(), 5)
    with pytest.raises(TimeoutError):
        await task
    assert released.is_set() and wire.closed
    assert record.status == "failed" and record.provider["stopped"]
    assert record.stages[-1]["status"] == "failed"
    assert close.await_count == (0 if blocked in {"prepare", "seed", "swallowed"} else 1)
    attempts = len(wire.calls)
    with pytest.raises(APIConnectionError):
        await adapters_seen[0].chat.complete(messages=[], tools=[])
    assert len(wire.calls) == attempts
    if blocked == "swallowed":
        assert [stage["name"] for stage in record.stages] == ["prepare"]


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
async def test_invalid_workflow_deadline_has_no_side_effects(timeout):
    wire, record = Wire(), RunRecord(str(uuid4()))
    callback = AsyncMock()
    with pytest.raises(ValueError, match="finite positive"):
        await run_business_acceptance(
            record, POLICY, api_key="offline", transport=wire,
            prepare=callback, seed=callback, exercise=callback, audit=callback,
            timeout=timeout,
        )
    callback.assert_not_awaited()
    assert record.status == "not_started" and not wire.calls and not wire.closed


@pytest.mark.parametrize("sku,week", [("", 202403), (" ", 202403), (None, 202403),
                                      ("sku", True), ("sku", 202153), ("sku", 202600)])
def test_database_audit_rejects_invalid_planned_scope(sku, week):
    from shared.acceptance.audit import database_audit

    context = AsyncMock()
    with pytest.raises(ValueError):
        database_audit(context, expectations=(), allowed_mention_ids=set(),
                       report_sku=sku, report_week=week)
    context.assert_not_called()
