"""FastAPI auth dependencies + quota enforcement.

Auth is optional everywhere: a request with no/invalid token is treated as an
anonymous "free" user keyed by client IP, so the public demo still works.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import select

from app.auth.security import decode_access_token, hash_api_key
from app.auth.tiers import quota_for
from app.db import repo
from app.db.database import get_session
from app.db.models import ApiKey, User


@dataclass
class Principal:
    user_id: Optional[int]
    email: str
    tier: str
    is_admin: bool
    is_anonymous: bool

    @property
    def quota_key(self) -> str:
        return f"user:{self.user_id}" if self.user_id else "anon"


def _principal_from_user(user: User) -> Principal:
    return Principal(
        user_id=user.id,
        email=user.email,
        tier=user.tier,
        is_admin=user.is_admin,
        is_anonymous=False,
    )


def _anonymous(request: Request) -> Principal:
    client = request.client.host if request.client else "unknown"
    return Principal(
        user_id=None,
        email=f"anon@{client}",
        tier="free",
        is_admin=False,
        is_anonymous=True,
    )


def optional_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> Principal:
    # 1) Bearer JWT
    if authorization and authorization.lower().startswith("bearer "):
        payload = decode_access_token(authorization.split(" ", 1)[1])
        if payload:
            user = repo.get_user(int(payload["sub"]))
            if user:
                return _principal_from_user(user)
    # 2) API key
    if x_api_key:
        with get_session() as s:
            row = s.exec(
                select(ApiKey).where(
                    ApiKey.key_hash == hash_api_key(x_api_key), ApiKey.revoked == False  # noqa: E712
                )
            ).first()
            if row:
                user = repo.get_user(row.user_id)
                if user:
                    return _principal_from_user(user)
    # 3) anonymous
    return _anonymous(request)


def current_user(principal: Principal = Depends(optional_user)) -> Principal:
    if principal.is_anonymous:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return principal


def require_admin(principal: Principal = Depends(optional_user)) -> Principal:
    if principal.is_anonymous or not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return principal


def enforce_quota(principal: Principal = Depends(optional_user)) -> Principal:
    """Increment and check the caller's daily quota; raise 429 when exceeded."""
    limit = quota_for(principal.tier)
    used = repo.increment_usage(principal.quota_key)
    if used > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily quota exceeded for tier '{principal.tier}' ({limit}/day). Upgrade to continue.",
        )
    return principal
