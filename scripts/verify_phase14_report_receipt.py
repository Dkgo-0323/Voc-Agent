"""Read-only report audit using this browser run's IDs, timestamp and content hash."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).absolute().parents[1]))

from shared.acceptance.reports import audit_report, validate_report_receipt


async def verify_report(receipt: dict, *, run_id: str) -> dict:
    last = validate_report_receipt(receipt, run_id=run_id)[-1]
    from backend.app.core.database import close_db, get_db_context, init_db
    from backend.app.db.repositories.report_repo import ReportRepository

    await init_db()
    try:
        async with get_db_context() as session:
            report = await ReportRepository(session).get_weekly_report(
                sku_code=last["sku_code"], week_id=last["week_id"]
            )
            return audit_report(receipt, report, run_id=run_id)
    finally:
        await close_db()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    print(json.dumps(asyncio.run(verify_report(receipt, run_id=args.run_id)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
