"""Borrow the running application's storage for exact-run, read-only audits."""

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ChatMessage
from backend.app.db.repositories.report_repo import ReportRepository
from shared.acceptance.receipts import (
    TurnExpectation,
    audit_turns,
    uuid_text,
    validate_receipt,
)
from shared.acceptance.reports import audit_report, validate_report_receipt


def database_audit(
    session_context: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    *,
    expectations: Sequence[TurnExpectation],
    allowed_mention_ids: set[str],
    report_sku: str,
    report_week: int,
):
    """Build a workflow audit callback, without initializing/disposing the DB.

    The caller supplies this dataset's expectations and allowed evidence, never
    implicit synthetic defaults. All session messages are loaded, so unexpected
    extra turns cannot be hidden by selecting only receipt message IDs. The
    callback issues reads only; the context owns transaction/session cleanup.
    No message body or report content is returned or retained in a run record.
    """
    if not isinstance(report_sku, str) or not report_sku.strip():
        raise ValueError("Invalid expected report SKU")
    if type(report_week) is not int:
        raise ValueError("Invalid expected report ISO week")
    date.fromisocalendar(report_week // 100, report_week % 100, 1)
    expected = tuple(expectations)
    allowed = {uuid_text(value) for value in allowed_mention_ids}
    if len(expected) != 5:
        raise ValueError("The workflow requires exactly five turn expectations")

    async def audit(ask: dict, reports: dict, run_id: str) -> None:
        turns = validate_receipt(ask, run_id=run_id)
        last = validate_report_receipt(reports, run_id=run_id)[-1]
        if last["sku_code"] != report_sku or last["week_id"] != report_week:
            raise ValueError("Report receipt differs from the planned SKU/week")
        if len(turns) != len(expected):
            raise ValueError("Receipt does not match the expected turn count")
        async with session_context() as session:
            messages = list((await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == UUID(turns[0]["session_id"]))
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )).all())
            audit_turns(
                ask, messages, expected, run_id=run_id, allowed_mention_ids=allowed,
            )
            stored = await ReportRepository(session).get_weekly_report(
                sku_code=last["sku_code"], week_id=last["week_id"],
            )
            audit_report(reports, stored, run_id=run_id)

    return audit
