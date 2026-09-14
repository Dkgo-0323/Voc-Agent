"""Validate locked SKU enablement and list active/inactive database metadata."""

import asyncio

from sqlalchemy import select

from backend.app.core.database import close_db, get_db_context, init_db
from backend.app.db.models import Sku
from backend.app.db.repositories.aspect_repo import AspectRepository
from pipelines.config.targets import LOCKED_SKU_CODES


async def main() -> None:
    await init_db()
    try:
        async with get_db_context() as session:
            await AspectRepository(session).validate_locked_skus(set(LOCKED_SKU_CODES))
            result = await session.execute(select(Sku).order_by(Sku.sku_code))
            rows = [
                {
                    "sku_code": sku.sku_code,
                    "dashboard_enabled": sku.dashboard_enabled,
                    "brand": sku.brand,
                    "model": sku.model,
                    "capacity_wh": sku.capacity_wh,
                    "capacity_tier": sku.capacity_tier,
                }
                for sku in result.scalars()
            ]
        print({"locked_sku_consistency": "passed", "skus": rows})
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
