# backend/app/core/settings.py
"""
应用全局配置，通过 Pydantic BaseSettings 从环境变量（.env）读取。
使用方式：from backend.app.core.settings import settings
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    所有配置项均可通过环境变量或 .env 文件覆盖。
    字段名与 .env.example 中的 key 一一对应（大小写不敏感）。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,   # DATABASE_URL 和 database_url 等价
        extra="ignore",         # 忽略 .env 中未声明的额外字段
    )

    # ── 应用基础 ──────────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_prefix: str = "/api/v1"

    # ── PostgreSQL ────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://voc:vocpassword@localhost:5432/vocdb",
        description="完整异步连接串，驱动必须为 asyncpg",
    )

    # ── Milvus ───────────────────────────────────────────────
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # ── Reddit API ───────────────────────────────────────────
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "voc-agent/0.1"

    # ── OpenAI ───────────────────────────────────────────────
    openai_api_key: str = ""

    # ── JWT ──────────────────────────────────────────────────
    jwt_secret_key: str = Field(
        default="dev-secret-key-replace-in-production",
        description="生产环境必须替换为随机 256-bit key",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # ── 管理员密码 ───────────────────────────────────────────
    admin_password: str = "change-me-in-production"

    # ── 计算属性 ─────────────────────────────────────────────
    @computed_field
    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @computed_field
    @property
    def sync_database_url(self) -> str:
        """
        Alembic 同步迁移用的连接串。
        将 asyncpg 驱动替换为标准 psycopg2，供 env.py 在同步上下文使用。
        注意：我们的 env.py 已配置异步模式，此属性仅作保留备用。
        """
        return self.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """生产环境强制检查敏感配置。"""
        if self.app_env == "production":
            if self.jwt_secret_key == "dev-secret-key-replace-in-production":
                raise ValueError(
                    "生产环境必须设置真实的 JWT_SECRET_KEY"
                )
            if self.admin_password == "change-me-in-production":
                raise ValueError(
                    "生产环境必须设置真实的 ADMIN_PASSWORD"
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    返回全局单例 Settings 实例。
    使用 lru_cache 确保 .env 只解析一次。
    FastAPI Depends 注入时使用此函数。
    """
    return Settings()


# 全局快捷访问（非 DI 场景直接 import 使用）
settings = get_settings()