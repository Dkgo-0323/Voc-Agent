"""Explicit subprocess callback for the shared HTTP bridge; no live defaults."""

from __future__ import annotations

import asyncio
import json
import math
import os
import signal
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

from shared.acceptance.receipts import uuid_text, validate_receipt
from shared.acceptance.reports import validate_report_receipt


async def _stop(process: asyncio.subprocess.Process) -> None:
    # Kill the process tree: Playwright owns Next and browser descendants too.
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(process.pid), "/T", "/F",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        await killer.wait()
    else:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    await process.wait()


def _read(path: Path) -> dict:
    # Bound allocation before parsing; receipts never need model response bodies.
    with path.open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("Browser receipt exceeds 64 KiB")
    return json.loads(data)


def browser_exercise(
    command: Sequence[str], *, cwd: Path, environment: Mapping[str, str],
    receipt_root: Path, timeout: float = 600,
):
    """Return a callback for http_exercise, using an explicitly supplied command.

    For Playwright use absolute node + CLI paths and the frontend cwd. Environment
    is passed verbatim (never inherited); caller owns approved target/password
    configuration. This adapter does not set live opt-in or authorize requests.
    Per-run temporary receipts are removed on every exit. Output is discarded to
    avoid retaining JWTs, prompts or provider errors; report only exit status.
    Callbacks/commands are trusted integration code, not a security sandbox.
    """
    if not command or not Path(command[0]).is_absolute():
        raise ValueError("Use an absolute executable path")
    if not cwd.is_absolute() or not receipt_root.is_absolute():
        raise ValueError("Use absolute working and receipt root paths")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Use a finite positive browser timeout")
    argv, env = tuple(command), dict(environment)

    async def run(base_url: str, run_id: str) -> tuple[dict, dict]:
        run_id = uuid_text(run_id)
        with tempfile.TemporaryDirectory(prefix="browser-", dir=receipt_root) as directory:
            child_env = {**env, "PHASE14_API_BASE_URL": base_url,
                         "PHASE14_RUN_ID": run_id, "PHASE14_RECEIPT_DIR": directory}
            options = ({"creationflags": subprocess.CREATE_NO_WINDOW}
                       if os.name == "nt" else {"start_new_session": True})
            process = await asyncio.create_subprocess_exec(
                *argv, cwd=cwd, env=child_env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout)
                if process.returncode != 0:
                    raise RuntimeError(f"Browser process exited with code {process.returncode}")
                ask = _read(Path(directory) / "ask-receipt.json")
                reports = _read(Path(directory) / "report-receipt.json")
                if len(validate_receipt(ask, run_id=run_id)) != 5:
                    raise ValueError("Expected exactly five browser Ask turns")
                validate_report_receipt(reports, run_id=run_id)
                return ask, reports
            finally:
                if process.returncode is None:
                    cleanup = asyncio.create_task(_stop(process))
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        await cleanup
                        raise

    return run
