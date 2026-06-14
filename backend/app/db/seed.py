import asyncio
from sqlalchemy import text

from backend.app.core.database import init_db, close_db, get_db_context

SKU_DATA = [
    {
        "brand":         "EcoFlow",
        "model":         "DELTA 2",
        "sku_code":      "ecoflow-delta2",
        "capacity_wh":   1024,
        "capacity_tier": "mid",
        "is_competitor": False,
    },
    {
        "brand":         "Jackery",
        "model":         "Explorer 1000",
        "sku_code":      "jackery-explorer-1000",
        "capacity_wh":   1002,
        "capacity_tier": "mid",
        "is_competitor": True,
    },
    {
        "brand":         "Jackery",
        "model":         "Explorer 300",
        "sku_code":      "jackery-explorer-300",
        "capacity_wh":   293,
        "capacity_tier": "entry",
        "is_competitor": True,
    },
    {
        "brand":         "Jackery",
        "model":         "Explorer 240",
        "sku_code":      "jackery-explorer-240",
        "capacity_wh":   240,
        "capacity_tier": "entry",
        "is_competitor": True,
    },
    {
        "brand":         "Anker",
        "model":         "SOLIX F2000",
        "sku_code":      "anker-solix-f2000",
        "capacity_wh":   2048,
        "capacity_tier": "large",
        "is_competitor": True,
    },
]


async def seed():
    await init_db()
    try:
        async with get_db_context() as session:
            for sku in SKU_DATA:
                await session.execute(
                    text("""
                        INSERT INTO skus (
                            id, brand, model, sku_code, category,
                            capacity_wh, capacity_tier, is_competitor, created_at
                        ) VALUES (
                            gen_random_uuid(), :brand, :model, :sku_code,
                            'portable-power-station',
                            :capacity_wh, :capacity_tier, :is_competitor,
                            NOW()
                        )
                        ON CONFLICT (sku_code) DO UPDATE SET
                            brand         = EXCLUDED.brand,
                            model         = EXCLUDED.model,
                            capacity_wh   = EXCLUDED.capacity_wh,
                            capacity_tier = EXCLUDED.capacity_tier,
                            is_competitor = EXCLUDED.is_competitor
                    """),
                    sku,
                )
        print(f"✅ Seed 完成，写入 {len(SKU_DATA)} 条 SKU")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(seed())