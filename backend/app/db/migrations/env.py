"""
Alembic env.py — 异步模式配置
关键点：必须使用 run_sync 包装，否则 asyncpg 不兼容
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# 导入 settings 和所有 ORM 模型（autogenerate 需要）
from backend.app.core.settings import settings
from backend.app.db.models import Base  # noqa: F401 — 触发所有模型注册

# Alembic Config 对象（读取 alembic.ini）
config = context.config

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 的元数据目标
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    离线模式：不需要真实DB连接，生成纯SQL脚本。
    CI/CD 环境或代码审查时使用。
    """
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # PostgreSQL 特有类型支持
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """同步执行迁移（在异步连接的 run_sync 中调用）"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # 检测字段类型变更
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    在线模式：创建异步引擎，用 run_sync 桥接同步迁移逻辑。
    这是 asyncpg 兼容的标准写法。
    """
    connectable = create_async_engine(
        settings.database_url,
        echo=False,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# 入口判断
if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())