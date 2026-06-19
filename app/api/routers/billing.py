"""Billing router (stub — tier plans + upgrade)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import Principal, current_user
from app.billing.service import checkout, list_plans

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/plans")
def plans() -> list[dict]:
    return list_plans()


@router.post("/checkout")
def upgrade(payload: dict, principal: Principal = Depends(current_user)) -> dict:
    tier = payload.get("tier", "")
    try:
        return checkout(principal.user_id, tier)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
