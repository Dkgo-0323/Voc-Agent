# backend/worker/main.py

import asyncio
import logging
from contextlib import suppress

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.app.core.database import close_db, init_db
from backend.app.core.settings import settings
from backend.worker.jobs import weekly_pipeline_job

logger = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler:
    """Build the production schedule without starting it (convenient for tests)."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        weekly_pipeline_job,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="UTC"),
        id="weekly_enrichment",
        name="Weekly Enrichment Pipeline",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    return scheduler


async def main():
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    logger.info("VOC Agent Worker 启动")

    await init_db()
    scheduler = build_scheduler()
    try:
        scheduler.start()
        logger.info("Scheduler 已启动：每周日 02:00 UTC")
        await asyncio.Event().wait()
    finally:
        logger.info("Worker 正在关闭...")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await close_db()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(main())
