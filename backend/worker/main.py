# backend/worker/main.py

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

async def placeholder_job():
    """Week 2 填充真实 pipeline 逻辑"""
    logger.info("Placeholder job triggered — Week 2 will implement enrichment here")

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    logger.info("VOC Agent Worker 启动")

    scheduler = AsyncIOScheduler()

    # 每周一 02:00 UTC 触发（Week 2 替换为真实 job）
    scheduler.add_job(
        placeholder_job,
        trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
        id="weekly_enrichment",
        name="Weekly Enrichment Pipeline",
    )

    scheduler.start()
    logger.info("Scheduler 已启动，等待触发...")

    try:
        await asyncio.Event().wait()   # 永久阻塞，直到 Ctrl+C
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker 收到退出信号，正在关闭...")
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())