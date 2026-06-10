# backend/app/main.py
"""
FastAPI 应用入口。

lifespan 事件管理：
  startup  → 初始化 DB 连接池
  shutdown → 释放 DB 连接池

当前暴露端点：
  GET /health  → 基础设施健康检查（DB 连通性）
"""
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.sql import text

from backend.app.core.database import close_db, get_engine, init_db
from backend.app.core.settings import settings

# ── 日志配置 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan（替代已废弃的 on_event） ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理。
    yield 之前：startup 逻辑
    yield 之后：shutdown 逻辑
    """
    # ── Startup ──
    logger.info(f"🚀 VOC Agent 启动中 [env={settings.app_env}]")
    await init_db()
    logger.info("✅ 所有基础设施初始化完成")

    yield  # ← 应用正常运行期间挂起在这里

    # ── Shutdown ──
    logger.info("🔻 VOC Agent 正在关闭...")
    await close_db()
    logger.info("👋 关闭完成")


# ── FastAPI 实例 ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="VOC Agent API",
    description="户外电源竞品舆情分析系统",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,   # 生产关闭 Swagger
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# ── CORS（开发阶段放开，生产收紧） ────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else ["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 路由 ──────────────────────────────────────────────────────────────────────
@app.get(
    "/health",
    tags=["Infrastructure"],
    summary="健康检查",
    response_model=dict[str, Any],
)
async def health_check() -> dict[str, Any]:
    """
    检查所有基础设施连通性：
    - PostgreSQL：执行 SELECT 1 + 返回版本号
    - 应用状态：运行时间

    返回 200 → 全部正常
    返回 503 → 部分/全部不可用
    """
    start = time.monotonic()
    checks: dict[str, Any] = {}
    all_healthy = True

    # ── PostgreSQL 检查 ──
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            pg_version = result.scalar()
        checks["postgresql"] = {
            "status": "healthy",
            "version": pg_version,
        }
    except Exception as e:
        logger.error(f"PostgreSQL 健康检查失败: {e}")
        checks["postgresql"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        all_healthy = False

    # ── 整体响应 ──
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    response = {
        "status": "healthy" if all_healthy else "unhealthy",
        "env": settings.app_env,
        "version": "0.1.0",
        "checks": checks,
        "elapsed_ms": elapsed_ms,
    }

    if not all_healthy:
        raise HTTPException(status_code=503, detail=response)

    return response