"""Database engine + session management."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import DATA_DIR, get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.resolved_database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        if url.startswith("sqlite"):
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, echo=False, connect_args=connect_args)
    return _engine


def init_db() -> None:
    # importing models registers them on SQLModel.metadata
    from app.db import models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())
    _seed_admin()


def _seed_admin() -> None:
    from app.auth.security import hash_password
    from app.db.models import User
    from sqlmodel import select

    settings = get_settings()
    with get_session() as session:
        existing = session.exec(select(User).where(User.email == settings.admin_email)).first()
        if existing:
            return
        admin = User(
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            full_name="Administrator",
            tier="enterprise",
            is_admin=True,
        )
        session.add(admin)
        session.commit()
        if settings.admin_password == "admin":
            print("[db] WARNING: default admin password in use — set ADMIN_PASSWORD in .env.")


@contextmanager
def get_session() -> Iterator[Session]:
    session = Session(get_engine())
    try:
        yield session
    finally:
        session.close()
