"""Validate exact report replacement receipts against the current stored row."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from shared.acceptance.receipts import uuid_text


def content_hash(report_md: str, summary: str) -> str:
    value = json.dumps([report_md, summary], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def timestamp(value: str | datetime) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return (
        result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    )


def validate_report_receipt(receipt: Mapping[str, Any], *, run_id: str) -> list[dict]:
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != 1:
        raise ValueError("Unsupported report receipt")
    if uuid_text(receipt.get("run_id")) != uuid_text(run_id):
        raise ValueError("Report receipt belongs to a different run")
    reports = receipt.get("reports")
    if not isinstance(reports, list) or len(reports) != 2:
        raise ValueError("Expected generation and regeneration receipts")
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("Invalid report receipt entry")
        uuid_text(report.get("report_id"))
        if (
            not isinstance(report.get("sku_code"), str)
            or not report["sku_code"]
            or type(report.get("week_id")) is not int
            or not isinstance(report.get("generated_at"), str)
            or not isinstance(report.get("content_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", report["content_sha256"])
        ):
            raise ValueError("Invalid report scope/content metadata")
        year, week = divmod(report["week_id"], 100)
        datetime.fromisocalendar(year, week, 1)
        timestamp(report["generated_at"])
    first, second = reports
    if any(first[key] != second[key] for key in ("report_id", "sku_code", "week_id")):
        raise ValueError("Regeneration changed the report identity/scope")
    if timestamp(second["generated_at"]) <= timestamp(first["generated_at"]):
        raise ValueError("Regeneration did not advance the report timestamp")
    return reports


def audit_report(receipt: Mapping[str, Any], stored: Any, *, run_id: str) -> dict:
    last = validate_report_receipt(receipt, run_id=run_id)[-1]
    if stored is None or any(
        str(getattr(stored, key)) != str(last[key])
        for key in ("report_id", "sku_code", "week_id")
    ):
        raise ValueError("Stored report identity/scope differs from this run")
    if timestamp(stored.generated_at) != timestamp(last["generated_at"]):
        raise ValueError("Stored report is stale or was replaced after this run")
    if not isinstance(stored.report_md, str) or not isinstance(stored.summary, str):
        raise ValueError("Stored report has no completed content")
    if content_hash(stored.report_md, stored.summary) != last["content_sha256"]:
        raise ValueError("Stored report content differs from this run")
    return {
        "schema_version": 1,
        "run_id": uuid_text(run_id),
        "report_id": last["report_id"],
        "verified_report_receipts": 2,
        "scope": "current stored report matches final receipt; no semantic quality assertion",
    }
