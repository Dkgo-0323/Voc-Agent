# pipelines/ingestion/amazon_loader.py

"""
Amazon Reviews 离线导入器
数据源：McAuley Amazon Reviews 2023 (Patio_Lawn_and_Garden.jsonl)
目标表：documents
去重：UNIQUE(platform, external_id) ON CONFLICT DO NOTHING
PII：author_hash = SHA256(user_id) 前16位，不存原始 user_id
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from backend.app.core.database import get_db_context, init_db, close_db
from pipelines.config.targets import REVIEW_FILE_PATH, TARGETS

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────
BATCH_SIZE   = 500    # 每批写入行数，平衡内存和往返次数
MIN_BODY_LEN = 20     # 过短评论直接丢弃（"Great!"之类无分析价值）


# ── 工具函数 ──────────────────────────────────────────────────────
def _hash_user(user_id: str) -> str:
    """SHA-256 取前16位，不可逆，满足 PII 脱敏要求"""
    if not user_id:
        return "anonymous"
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


def _parse_ts(ts) -> datetime | None:
    """兼容 int(ms) / int(s) / str ISO 格式时间戳"""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            # 毫秒级时间戳
            ts_sec = ts / 1000 if ts > 1e10 else ts
            return datetime.fromtimestamp(ts_sec, tz=timezone.utc)
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def _iso_week(dt: datetime | None) -> int:
    """转为 YYYYWW 格式，如 202408，None 时返回当前周"""
    if dt is None:
        dt = datetime.now(timezone.utc)
    iso = dt.isocalendar()          # (year, week, weekday)
    return iso[0] * 100 + iso[1]    # e.g. 2024 * 100 + 8 = 202408


def _build_asin_index() -> dict[str, str]:
    """
    返回 {asin_or_parent: sku_code}
    loader 对每条 review 的 asin 和 parent_asin 都查这张表
    """
    index: dict[str, str] = {}
    for sku_code, cfg in TARGETS.items():
        for asin in cfg["amazon_asins"]:
            index[asin] = sku_code
    return index


# ── 主流程 ────────────────────────────────────────────────────────
async def _get_sku_id_map(session) -> dict[str, str]:
    """从数据库查 sku_code → id 映射"""
    rows = await session.execute(text("SELECT sku_code, id FROM skus"))
    return {row.sku_code: str(row.id) for row in rows}


async def _insert_batch(session, batch: list[dict]) -> tuple[int, int]:
    """
    批量插入，返回 (inserted, skipped)
    ON CONFLICT DO NOTHING 保证幂等
    """
    if not batch:
        return 0, 0

    result = await session.execute(
        text("""
            INSERT INTO documents (
                id, sku_id, platform, external_id,
                title, body, rating,
                author_hash, source_url,
                published_at, week_id, ingested_at
            )
            SELECT
                gen_random_uuid(),
                d.sku_id, d.platform, d.external_id,
                d.title, d.body, d.rating,
                d.author_hash, d.source_url,
                d.published_at, d.week_id, NOW()
            FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS d(
                sku_id       uuid,
                platform     text,
                external_id  text,
                title        text,
                body         text,
                rating       smallint,
                author_hash  text,
                source_url   text,
                published_at timestamptz,
                week_id      int
            )
            ON CONFLICT (platform, external_id) DO NOTHING
        """),
        {"rows": json.dumps(batch)},
    )
    inserted = result.rowcount
    skipped  = len(batch) - inserted
    return inserted, skipped


async def load_amazon_reviews(
    file_path: str | None = None,
    limit: int | None = None,          # 调试用：只处理前N条
    dry_run: bool = False,             # True时只扫描不写库
) -> dict:
    """
    主入口函数
    Returns: {"total_scanned", "inserted", "skipped", "no_sku_match", "too_short"}
    """
    path = Path(file_path or REVIEW_FILE_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Review 文件不存在: {path}")

    asin_index = _build_asin_index()
    logger.info(f"ASIN 索引已建立，共 {len(asin_index)} 个 ASIN 映射到 {len(TARGETS)} 个 SKU")

    stats = {
        "total_scanned": 0,
        "inserted":      0,
        "skipped":       0,   # 重复，ON CONFLICT跳过
        "no_sku_match":  0,   # ASIN不在目标列表
        "too_short":     0,   # body太短
    }

    await init_db()
    try:
        async with get_db_context() as session:
            sku_id_map = await _get_sku_id_map(session)
            logger.info(f"SKU映射已加载: {list(sku_id_map.keys())}")

            batch: list[dict] = []

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for raw_line in f:
                    # ── 解析 ──────────────────────────────────────────
                    try:
                        review = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    stats["total_scanned"] += 1
                    if limit and stats["total_scanned"] > limit:
                        break

                    if stats["total_scanned"] % 500_000 == 0:
                        logger.info(
                            f"进度 {stats['total_scanned']:,} | "
                            f"已插入 {stats['inserted']:,} | "
                            f"跳过 {stats['skipped']:,}"
                        )

                    # ── ASIN 匹配（child 和 parent 都查）────────────
                    asin        = review.get("asin", "")
                    parent_asin = review.get("parent_asin", "")
                    sku_code    = asin_index.get(asin) or asin_index.get(parent_asin)

                    if not sku_code:
                        stats["no_sku_match"] += 1
                        continue

                    sku_id = sku_id_map.get(sku_code)
                    if not sku_id:
                        # SKU 在 targets.py 里有但数据库没有 seed → 跳过并警告
                        logger.warning(f"sku_code [{sku_code}] 不在数据库中，请先运行 seed.py")
                        continue

                    # ── 正文过滤 ──────────────────────────────────────
                    body = (review.get("text") or "").strip()
                    if len(body) < MIN_BODY_LEN:
                        stats["too_short"] += 1
                        continue

                    # ── 字段提取 ──────────────────────────────────────
                    published_at = _parse_ts(review.get("timestamp"))
                    week_id      = _iso_week(published_at)
                    rating_raw   = review.get("rating")
                    rating       = int(rating_raw) if rating_raw is not None else None

                    # external_id：优先用 review_id，没有就用 asin+user_id 拼合
                    review_id   = review.get("review_id") or review.get("id", "")
                    user_id     = review.get("user_id", "")
                    external_id = review_id or f"{asin}_{user_id}"

                    row = {
                        "sku_id":       sku_id,
                        "platform":     "amazon",
                        "external_id":  external_id,
                        "title":        (review.get("title") or "")[:500],   # 防超长
                        "body":         body,
                        "rating":       rating,
                        "author_hash":  _hash_user(user_id),
                        "source_url":   f"https://www.amazon.com/dp/{asin}",
                        "published_at": published_at.isoformat() if published_at else None,
                        "week_id":      week_id,
                    }

                    batch.append(row)

                    # ── 批量写入 ──────────────────────────────────────
                    if len(batch) >= BATCH_SIZE and not dry_run:
                        inserted, skipped = await _insert_batch(session, batch)
                        await session.commit()
                        stats["inserted"] += inserted
                        stats["skipped"]  += skipped
                        batch.clear()

            # ── 最后一批 ──────────────────────────────────────────────
            if batch and not dry_run:
                inserted, skipped = await _insert_batch(session, batch)
                await session.commit()
                stats["inserted"] += inserted
                stats["skipped"]  += skipped
    finally:
        await close_db()

    return stats


# ── CLI 入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Amazon Review Loader")
    parser.add_argument("--limit",   type=int,  default=None,  help="只处理前N条（调试用）")
    parser.add_argument("--dry-run", action="store_true",      help="只扫描不写库")
    args = parser.parse_args()

    async def main():
        logger.info("=== Amazon Review Loader 启动 ===")
        stats = await load_amazon_reviews(
            limit=args.limit,
            dry_run=args.dry_run,
        )
        logger.info("=== 完成 ===")
        logger.info(f"  扫描总行数  : {stats['total_scanned']:>8,}")
        logger.info(f"  成功插入    : {stats['inserted']:>8,}")
        logger.info(f"  重复跳过    : {stats['skipped']:>8,}")
        logger.info(f"  ASIN不匹配  : {stats['no_sku_match']:>8,}")
        logger.info(f"  正文过短    : {stats['too_short']:>8,}")

    asyncio.run(main())