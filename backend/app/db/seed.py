"""
SKU 初始数据写入脚本
运行方式：python -m backend.app.db.seed
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 修改点 1：导入 init_db 和 get_db_context
from backend.app.core.database import init_db, get_db_context
from backend.app.db.models import Sku

# ──────────────────────────────────────────────
# 已锁定 SKU 数据（对应文档 Section 3）
# ──────────────────────────────────────────────
SKU_DATA = [
    {
        "brand": "EcoFlow",
        "model": "DELTA 2",
        "sku_code": "ecoflow-delta2",
        "capacity_wh": 1024,
        "capacity_tier": "mid",
        "is_competitor": False,  # 自家产品
    },
    {
        "brand": "Jackery",
        "model": "Explorer 300",
        "sku_code": "jackery-explorer-300",
        "capacity_wh": 292,
        "capacity_tier": "entry",
        "is_competitor": True,
    },
    {
        "brand": "Jackery",
        "model": "Explorer 1000 v2",
        "sku_code": "jackery-explorer-1000",
        "capacity_wh": 1070,
        "capacity_tier": "mid",
        "is_competitor": True,
    },
    {
        "brand": "DJI",
        "model": "Power 1000",
        "sku_code": "dji-power-1000",
        "capacity_wh": 1024,
        "capacity_tier": "mid",
        "is_competitor": True,
    },
    {
        "brand": "Anker",
        "model": "SOLIX C300",
        "sku_code": "anker-solix-c300",
        "capacity_wh": 288,
        "capacity_tier": "entry",
        "is_competitor": True,
    },
]


async def seed_skus(session: AsyncSession) -> None:
    """写入 SKU 数据，已存在则跳过（幂等）"""
    inserted = 0
    skipped = 0

    for data in SKU_DATA:
        # 检查是否已存在
        result = await session.execute(
            select(Sku).where(Sku.sku_code == data["sku_code"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"  SKIP  {data['sku_code']} (already exists)")
            skipped += 1
            continue

        sku = Sku(
            id=uuid.uuid4(),
            brand=data["brand"],
            model=data["model"],
            sku_code=data["sku_code"],
            category="portable-power-station",
            capacity_wh=data["capacity_wh"],
            capacity_tier=data["capacity_tier"],
            is_competitor=data["is_competitor"],
        )
        session.add(sku)
        print(f"  INSERT {data['sku_code']}")
        inserted += 1

    await session.commit()
    print(f"\n✅ Seed complete: {inserted} inserted, {skipped} skipped")


async def main() -> None:
    print("🌱 Seeding SKU data...\n")
    
    # 修改点 2：在非 FastAPI 环境下启动脚本，必须先手动建立数据库连接池
    await init_db()
    
    # 修改点 3：替换为 get_db_context() 上下文管理器
    async with get_db_context() as session:
        await seed_skus(session)


if __name__ == "__main__":
    asyncio.run(main())