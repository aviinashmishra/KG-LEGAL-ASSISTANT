"""Auth + account router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import Principal, current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.auth.tiers import quota_for
from app.db import repo
from app.schemas import (
    AccountResponse,
    LoginRequest,
    SignupRequest,
    TokenResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
def signup(req: SignupRequest) -> TokenResponse:
    if repo.get_user_by_email(req.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    if len(req.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    user = repo.create_user(req.email, hash_password(req.password), req.full_name)
    token = create_access_token(user.id, user.email, user.is_admin)
    return TokenResponse(access_token=token, tier=user.tier, is_admin=user.is_admin)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    user = repo.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.id, user.email, user.is_admin)
    return TokenResponse(access_token=token, tier=user.tier, is_admin=user.is_admin)


@router.get("/me", response_model=AccountResponse)
def me(principal: Principal = Depends(current_user)) -> AccountResponse:
    return AccountResponse(
        email=principal.email,
        tier=principal.tier,
        is_admin=principal.is_admin,
        usage_today=repo.get_usage(principal.quota_key),
        daily_quota=quota_for(principal.tier),
    )
