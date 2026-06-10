# backend/app/core/database.py
"""
异步数据库引擎和会话工厂。

设计说明：
- 使用 SQLAlchemy 2.0 asyncio 模式
- engine 在应用启动时创建，关闭时 dispose
- get_db() 作为 FastAPI Depends 注入，每个请求独立 session，自动提交/回滚
- get_db_context() 供非 HTTP 场景（Worker、脚本）使用
"""
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from backend.app.core.settings import settings

logger = logging.getLogger(__name__)

# ── 引擎配置 ──────────────────────────────────────────────────────────────────
def _build_engine() -> AsyncEngine:
    """
    构建异步引擎。
    pool_size / max_overflow：MVP 阶段保守配置，够用即可。
    echo：仅在 development 模式下打印 SQL（方便调试）。
    """
    return create_async_engine(
        settings.database_url,
        echo=settings.is_development,       # True → 控制台打印所有 SQL
        pool_size=10,                        # 常驻连接数
        max_overflow=20,                     # 峰值额外连接数
        pool_pre_ping=True,                  # 每次取连接前 PING，防止陈旧连接
        pool_recycle=3600,                   # 1小时回收连接，防止 PG 端超时断开
    )


# 模块级单例：import 时不立刻创建，等 lifespan 调用
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """返回全局 engine，未初始化时抛出明确错误。"""
    if _engine is None:
        raise RuntimeError(
            "数据库引擎未初始化，请确保 lifespan 事件已触发（FastAPI startup）"
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _async_session_factory is None:
        raise RuntimeError("Session factory 未初始化")
    return _async_session_factory


# ── 生命周期管理 ──────────────────────────────────────────────────────────────
async def init_db() -> None:
    """
    应用启动时调用。
    创建 engine 和 session factory。
    不执行建表（建表由 Alembic 管理）。
    """
    global _engine, _async_session_factory

    logger.info("正在初始化数据库连接池...")
    _engine = _build_engine()
    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,  # commit 后对象属性不过期，避免额外查询
        autocommit=False,
        autoflush=False,
    )

    # 验证连接可用性
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ 数据库连接成功")
    except Exception as e:
        logger.error(f"❌ 数据库连接失败: {e}")
        raise


async def close_db() -> None:
    """应用关闭时调用，释放连接池。"""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        logger.info("数据库连接池已关闭")
        _engine = None


# ── FastAPI Depends 注入 ───────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 路由层依赖注入。

    用法：
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...

    事务边界：
        - 正常退出 → commit
        - 异常退出 → rollback
        - 无论如何 → session.close()
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── 非 HTTP 场景上下文管理器 ──────────────────────────────────────────────────
@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Worker / 脚本 / 测试中使用的上下文管理器。

    用法：
        async with get_db_context() as db:
            result = await db.execute(select(Sku))
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise