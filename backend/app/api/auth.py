"""Minimal configured-password JWT endpoints for the Week 3 demo API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.security import (
    create_access_token,
    get_request_identity,
    verify_configured_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

ADMIN_SUBJECT = "admin"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=1_024)


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthIdentityResponse(BaseModel):
    subject: str


@router.post("/login", response_model=AccessTokenResponse)
async def login(payload: LoginRequest) -> AccessTokenResponse:
    if not verify_configured_password(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AccessTokenResponse(access_token=create_access_token(ADMIN_SUBJECT))


@router.get("/me", response_model=AuthIdentityResponse)
async def current_identity(
    identity: Annotated[str, Depends(get_request_identity)],
) -> AuthIdentityResponse:
    return AuthIdentityResponse(subject=identity)
