"""Thin repository helpers over the SQLModel session."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import select

from app.db.database import get_session
from app.db.models import (
    Conversation,
    Invoice,
    Message,
    QueryLog,
    SavedResearch,
    UsageCounter,
    User,
)


# ---------------- users ----------------
def get_user_by_email(email: str) -> Optional[User]:
    with get_session() as s:
        return s.exec(select(User).where(User.email == email)).first()


def get_user(user_id: int) -> Optional[User]:
    with get_session() as s:
        return s.get(User, user_id)


def create_user(email: str, password_hash: str, full_name: str = "") -> User:
    with get_session() as s:
        user = User(email=email, password_hash=password_hash, full_name=full_name)
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


def set_tier(user_id: int, tier: str) -> None:
    with get_session() as s:
        user = s.get(User, user_id)
        if user:
            user.tier = tier
            s.add(user)
            s.commit()


# ---------------- conversations / messages ----------------
def create_conversation(user_id: Optional[int], title: str) -> Conversation:
    with get_session() as s:
        conv = Conversation(user_id=user_id, title=title[:80] or "New conversation")
        s.add(conv)
        s.commit()
        s.refresh(conv)
        return conv


def add_message(conversation_id: int, role: str, content: str, **kw) -> Message:
    with get_session() as s:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            confidence=kw.get("confidence", ""),
            hallucination_score=kw.get("hallucination_score", 0.0),
            citations_json=json.dumps(kw.get("citations", [])),
            kg_nodes_json=json.dumps(kw.get("kg_nodes", [])),
        )
        s.add(msg)
        s.commit()
        s.refresh(msg)
        return msg


def list_conversations(user_id: int, limit: int = 50) -> list[Conversation]:
    with get_session() as s:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        return list(s.exec(stmt))


def list_messages(conversation_id: int) -> list[Message]:
    with get_session() as s:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(s.exec(stmt))


# ---------------- saved research ----------------
def save_research(user_id: int, title: str, query: str, answer: str, payload: dict) -> SavedResearch:
    with get_session() as s:
        item = SavedResearch(
            user_id=user_id, title=title[:120], query=query, answer=answer,
            payload_json=json.dumps(payload),
        )
        s.add(item)
        s.commit()
        s.refresh(item)
        return item


def list_saved(user_id: int) -> list[SavedResearch]:
    with get_session() as s:
        stmt = (
            select(SavedResearch)
            .where(SavedResearch.user_id == user_id)
            .order_by(SavedResearch.created_at.desc())
        )
        return list(s.exec(stmt))


# ---------------- query log / metrics ----------------
def log_query(**kw) -> None:
    with get_session() as s:
        s.add(QueryLog(**kw))
        s.commit()


def recent_query_logs(limit: int = 1000) -> list[QueryLog]:
    with get_session() as s:
        stmt = select(QueryLog).order_by(QueryLog.created_at.desc()).limit(limit)
        return list(s.exec(stmt))


# ---------------- usage / quota ----------------
def increment_usage(user_key: str) -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_session() as s:
        row = s.exec(
            select(UsageCounter).where(
                UsageCounter.user_key == user_key, UsageCounter.day == day
            )
        ).first()
        if not row:
            row = UsageCounter(user_key=user_key, day=day, count=0)
        row.count += 1
        s.add(row)
        s.commit()
        return row.count


def get_usage(user_key: str) -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_session() as s:
        row = s.exec(
            select(UsageCounter).where(
                UsageCounter.user_key == user_key, UsageCounter.day == day
            )
        ).first()
        return row.count if row else 0


# ---------------- billing ----------------
def record_invoice(user_id: int, tier: str, amount_inr: int) -> Invoice:
    with get_session() as s:
        inv = Invoice(user_id=user_id, tier=tier, amount_inr=amount_inr, status="paid")
        s.add(inv)
        s.commit()
        s.refresh(inv)
        return inv
