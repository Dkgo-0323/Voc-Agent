# backend/app/core/security.py
"""
JWT 签发与验证骨架。
Week 1 仅建立结构，Week 2 接入鉴权中间件时完善。
"""

from datetime import UTC, datetime, timedelta
from secrets import compare_digest
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from jose import jwt
from passlib.context import CryptContext

from backend.app.core.settings import settings

# ── 密码哈希 ──────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_configured_password(password: str) -> bool:
    """Compare the single configured MVP password without a user store."""

    return compare_digest(password, settings.admin_password)


# ── JWT ──────────────────────────────────────────────────────────────────────
def create_access_token(
    subject: str | Any,
    expires_delta: timedelta | None = None,
) -> str:
    """
    签发 JWT Token。
    subject：通常是用户标识（MVP 阶段固定为 "admin"）
    """
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(days=settings.jwt_expire_days)
    )
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(UTC),
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


async def get_request_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Return the verified JWT subject for the small protected API surface."""

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required or the access token is invalid.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise unauthorized from exc
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise unauthorized
    return subject
