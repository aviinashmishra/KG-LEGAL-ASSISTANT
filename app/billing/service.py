"""Billing service stub.

Simulates a successful checkout: records an invoice and upgrades the user's tier.
No real payment processor is contacted (see plan scope boundaries).
"""
from __future__ import annotations

from app.auth.tiers import price_for, tier_catalog
from app.db import repo


def list_plans() -> list[dict]:
    return [
        {
            "tier": t.name,
            "label": t.label,
            "price_inr_month": t.price_inr_month,
            "daily_quota": t.daily_quota,
        }
        for t in tier_catalog().values()
    ]


def checkout(user_id: int, tier: str) -> dict:
    if tier not in tier_catalog():
        raise ValueError(f"Unknown tier: {tier}")
    amount = price_for(tier)
    invoice = repo.record_invoice(user_id=user_id, tier=tier, amount_inr=amount)
    repo.set_tier(user_id, tier)
    return {
        "status": "success",
        "tier": tier,
        "amount_inr": amount,
        "invoice_id": invoice.id,
        "message": f"Upgraded to {tier}. (Billing is a demo stub — no card was charged.)",
    }
