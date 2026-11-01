"""Actual local child processes, synthetic receipts, no browser/provider/storage."""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from shared.acceptance.browser import browser_exercise


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ok", "exit", "missing", "stale", "oversize", "timeout", "cancel"])
async def test_browser_process_receipts_and_cleanup(tmp_path, monkeypatch, mode):
    run_id, session = str(uuid4()), str(uuid4())
    ask = {"schema_version": 1, "run_id": run_id, "turns": [
        {"session_id": session, "user_message_id": str(uuid4()),
         "assistant_message_id": str(uuid4())} for _ in range(5)
    ]}
    report = {"report_id": str(uuid4()), "sku_code": "test", "week_id": 202403,
              "generated_at": "2026-11-01T00:00:00Z", "content_sha256": "a" * 64}
    reports = {"schema_version": 1, "run_id": run_id, "reports": [
        report, {**report, "generated_at": "2026-11-01T00:00:01Z"}
    ]}
    script = tmp_path / "child.py"
    script.write_text('''import json, os, pathlib, sys, time
root = pathlib.Path(os.environ["PHASE14_RECEIPT_DIR"])
mode = sys.argv[1]
assert os.environ["PHASE14_API_BASE_URL"] == "http://127.0.0.1:12345"
assert "VOC_PARENT_SECRET" not in os.environ
if mode in ("timeout", "cancel"):
    time.sleep(60)
if mode == "exit":
    sys.exit(7)
ask, reports = json.loads(sys.argv[2]), json.loads(sys.argv[3])
assert ask["run_id"] == os.environ["PHASE14_RUN_ID"]
if mode == "stale":
    ask["run_id"] = "00000000-0000-0000-0000-000000000000"
(root / "ask-receipt.json").write_text(json.dumps(ask))
if mode != "missing":
    (root / "report-receipt.json").write_text("x" * 65537 if mode == "oversize" else json.dumps(reports))
''', encoding="utf-8")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    monkeypatch.setenv("VOC_PARENT_SECRET", "must-not-inherit")
    children = []
    original = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        if args[0] == sys.executable:
            children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    callback = browser_exercise(
        [sys.executable, str(script), mode, json.dumps(ask), json.dumps(reports)],
        cwd=tmp_path, environment={key: value for key, value in os.environ.items()
                                   if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH"}},
        receipt_root=receipts, timeout=0.1 if mode == "timeout" else 10,
    )
    task = asyncio.create_task(callback("http://127.0.0.1:12345", run_id))
    if mode == "cancel":
        while not children:
            await asyncio.sleep(0.01)
        task.cancel()
    errors = {"exit": RuntimeError, "missing": FileNotFoundError, "stale": ValueError,
              "oversize": ValueError, "timeout": TimeoutError, "cancel": asyncio.CancelledError}
    if mode == "ok":
        assert await task == (ask, reports)
    else:
        with pytest.raises(errors[mode]):
            await task
    assert len(children) == 1 and children[0].returncode is not None
    assert list(receipts.iterdir()) == []


def test_browser_configuration_rejects_unsafe_defaults(tmp_path):
    with pytest.raises(ValueError, match="absolute executable"):
        browser_exercise(["node"], cwd=tmp_path, environment={}, receipt_root=tmp_path)
    with pytest.raises(ValueError, match="finite positive"):
        browser_exercise([str(Path(sys.executable))], cwd=tmp_path, environment={},
                         receipt_root=tmp_path, timeout=float("inf"))
