"""Single-process acceptance orchestration; no CLI, credentials or default wire.

Callbacks are trusted integration code, not a sandbox. They must use the supplied
adapters/app; legacy subprocess launchers are deliberately not called here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import httpx
from fastapi import FastAPI

from backend.app.main import create_app
from shared.acceptance.receipts import uuid_text, validate_receipt
from shared.acceptance.reports import validate_report_receipt
from shared.acceptance.runtime import AcceptanceAdapters, acceptance_adapters
from shared.acceptance.transport import AcceptanceStopped, ProviderPolicy

Prepare = Callable[[AcceptanceAdapters], Awaitable[None]]
Exercise = Callable[[FastAPI, str], Awaitable[tuple[dict, dict]]]
Audit = Callable[[dict, dict, str], Awaitable[None]]


@dataclass
class RunRecord:
    """Allowlisted diagnostics survive failure/cancellation, without error text."""

    run_id: str
    status: str = "not_started"
    stages: list[dict[str, Any]] = field(default_factory=list)
    provider: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.run_id = uuid_text(self.run_id)


async def run_business_acceptance(
    record: RunRecord,
    policy: ProviderPolicy,
    *,
    api_key: str,
    transport: httpx.AsyncBaseTransport,
    prepare: Prepare,
    seed: Prepare,
    exercise: Exercise,
    audit: Audit,
) -> None:
    """Prepare, seed twice, start one API, exercise and audit under one guard.

    The caller supplies approved data/isolated storage and the browser/server
    integration. Exercise receives an already-started app: it must not start its
    lifespan again or construct another API. Audit must raise on mismatch. This
    function does not authorize live use, implement a monetary cap, or roll back
    writes from an earlier completed stage. No callback output is kept in record.
    """
    if record.status != "not_started" or record.stages or record.provider is not None:
        raise ValueError("A run record cannot be reused")
    if policy.chat_requests > 72 or policy.embedding_requests > 24:
        raise ValueError("Replan before increasing the proposed 72/24 allowances")
    record.status = "running"
    adapters = None

    async def stage(name: str, action: Callable[[], Awaitable[Any]]) -> Any:
        started = monotonic()
        entry = {"name": name, "status": "running"}
        record.stages.append(entry)
        try:
            if adapters.guard.summary()["stopped"]:
                raise AcceptanceStopped("A previous acceptance stage stopped the run")
            value = await action()
            # A callback may catch a provider failure; that must not advance us.
            if adapters.guard.summary()["stopped"]:
                raise AcceptanceStopped("Acceptance stage returned after a failure")
            entry["status"] = "completed"
            return value
        except BaseException:
            entry["status"] = "failed"
            adapters.guard.stop()
            raise
        finally:
            entry["elapsed_ms"] = round((monotonic() - started) * 1000, 2)
            record.provider = adapters.guard.summary()

    try:
        async with acceptance_adapters(
            policy, api_key=api_key, transport=transport,
        ) as adapters:
            try:
                await stage("prepare", lambda: prepare(adapters))
                await stage("seed", lambda: seed(adapters))
                await stage("repeat_seed", lambda: seed(adapters))

                async def api() -> None:
                    app = create_app(acceptance_adapters=adapters)
                    async with app.router.lifespan_context(app):
                        # Startup probe is included in this same guard.
                        receipts = await stage("exercise", lambda: exercise(app, record.run_id))

                        async def check() -> None:
                            ask, reports = receipts
                            turns = validate_receipt(ask, run_id=record.run_id)
                            if len(turns) != 5:
                                raise ValueError("Expected exactly five Ask turns")
                            validate_report_receipt(reports, run_id=record.run_id)
                            await audit(ask, reports, record.run_id)

                        await stage("audit", check)

                await stage("api", api)
            except BaseException:
                adapters.guard.stop()
                raise
    except BaseException:
        record.status = "failed"
        if adapters is not None:
            adapters.guard.stop()
        raise
    else:
        record.status = "completed"
    finally:
        if adapters is not None:
            record.provider = adapters.guard.summary()
