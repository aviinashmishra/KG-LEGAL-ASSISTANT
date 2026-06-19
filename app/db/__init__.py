"""Persistence layer (SQLModel; SQLite by default, Postgres via DATABASE_URL)."""

from app.db.database import get_session, init_db

__all__ = ["init_db", "get_session"]
