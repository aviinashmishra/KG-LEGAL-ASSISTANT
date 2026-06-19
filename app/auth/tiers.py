"""Subscription tiers + per-day quota logic."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass
class TierInfo:
    name: str
    daily_quota: int
    price_inr_month: int
    label: str


def tier_catalog() -> dict[str, TierInfo]:
    s = get_settings()
    return {
        "free": TierInfo("free", s.quota_free, 0, "Free"),
        "pro": TierInfo("pro", s.quota_pro, 999, "Pro"),
        "enterprise": TierInfo("enterprise", s.quota_enterprise, 50000, "Enterprise"),
    }


def quota_for(tier: str) -> int:
    return tier_catalog().get(tier, tier_catalog()["free"]).daily_quota


def price_for(tier: str) -> int:
    return tier_catalog().get(tier, tier_catalog()["free"]).price_inr_month
