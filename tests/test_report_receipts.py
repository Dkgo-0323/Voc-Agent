from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from shared.acceptance.reports import (
    audit_report,
    content_hash,
    validate_report_receipt,
)


def fixture():
    run_id, report_id = str(uuid4()), str(uuid4())
    # Shared with the TS receipt test: UTF-8/JSON array hashing must agree.
    stored = SimpleNamespace(
        report_id=report_id,
        sku_code="ecoflow-delta2",
        week_id=202403,
        generated_at="2026-10-22T04:00:00Z",
        report_md="private report",
        summary="摘要",
    )
    last = dict(
        report_id=report_id,
        sku_code=stored.sku_code,
        week_id=stored.week_id,
        generated_at=stored.generated_at,
        content_sha256=content_hash(stored.report_md, stored.summary),
    )
    first = {**last, "generated_at": "2026-10-22T03:59:00"}
    return dict(schema_version=1, run_id=run_id, reports=[first, last]), stored, run_id


def test_report_row_matches_final_replacement_without_leaking_content():
    receipt, stored, run_id = fixture()
    report = audit_report(receipt, stored, run_id=run_id)
    assert report["verified_report_receipts"] == 2
    assert "private report" not in str(report)
    assert (
        content_hash("private report", "摘要")
        == "4a223d027b1f83dd733f7e6d0e843260d9a15f16ca58aac3c6c402c7193a69bd"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "run",
        "id",
        "scope",
        "timestamp",
        "stale",
        "hash",
        "invalid_week",
        "absent_row",
        "missing_content",
    ],
)
def test_stale_wrong_or_failed_replacements_do_not_pass(mutation):
    receipt, stored, run_id = fixture()
    if mutation == "run":
        run_id = str(uuid4())
    elif mutation == "id":
        stored.report_id = str(uuid4())
    elif mutation == "scope":
        receipt["reports"][1]["sku_code"] = "jackery-explorer-1000"
    elif mutation == "timestamp":
        receipt["reports"][1]["generated_at"] = receipt["reports"][0]["generated_at"]
    elif mutation == "stale":
        stored.generated_at = "2026-10-21T04:00:00Z"
    elif mutation == "hash":
        stored.summary = "different"
    elif mutation == "invalid_week":
        receipt["reports"][1]["week_id"] = 202454
    elif mutation == "absent_row":
        stored = None
    elif mutation == "missing_content":
        stored.report_md = None
    with pytest.raises(ValueError):
        audit_report(receipt, stored, run_id=run_id)


def test_single_report_is_not_regeneration_evidence():
    receipt, _, run_id = fixture()
    receipt = deepcopy(receipt)
    receipt["reports"].pop()
    with pytest.raises(ValueError):
        validate_report_receipt(receipt, run_id=run_id)
