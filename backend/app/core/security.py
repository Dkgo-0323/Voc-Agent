# backend/app/core/security.py
"""
JWT 签发与验证骨架。
Week 1 仅建立结构，Week 2 接入鉴权中间件时完善。
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.app.core.settings import settings

# ── 密码哈希 ──────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# ── JWT ──────────────────────────────────────────────────────────────────────
def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """
    签发 JWT Token。
    subject：通常是用户标识（MVP 阶段固定为 "admin"）
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.jwt_expire_days)
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    解码并验证 JWT Token。
    无效/过期时抛出 JWTError。
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )