"""Database models (SQLModel)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    full_name: str = ""
    tier: str = Field(default="free")  # free | pro | enterprise
    is_admin: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    key_hash: str = Field(index=True)
    prefix: str = Field(index=True)  # first 8 chars, for display/lookup
    label: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    revoked: bool = False


class Conversation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    title: str = "New conversation"
    created_at: datetime = Field(default_factory=_utcnow)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(index=True)
    role: str  # user | assistant
    content: str
    confidence: str = ""
    hallucination_score: float = 0.0
    citations_json: str = "[]"
    kg_nodes_json: str = "[]"
    created_at: datetime = Field(default_factory=_utcnow)


class SavedResearch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    title: str
    query: str
    answer: str
    payload_json: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


class QueryLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    query: str
    intent: str = ""
    confidence: str = ""
    hallucination_score: float = 0.0
    latency_ms: int = 0
    llm_provider: str = ""
    cache_hit: bool = False
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class UsageCounter(SQLModel, table=True):
    """Per-user per-day query counter for quota enforcement."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_key: str = Field(index=True)  # user_id or anonymous client id
    day: str = Field(index=True)  # YYYY-MM-DD (UTC)
    count: int = 0


class Invoice(SQLModel, table=True):
    """Billing stub — records tier upgrades (no real payment processor)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    tier: str
    amount_inr: int = 0
    status: str = "paid"  # stub: immediately "paid"
    created_at: datetime = Field(default_factory=_utcnow)
