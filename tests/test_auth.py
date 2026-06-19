import uuid

import pytest

from app.auth.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)
    assert h != hash_password("secret123")  # salted


def test_jwt_roundtrip():
    token = create_access_token(7, "a@b.com", is_admin=True)
    payload = decode_access_token(token)
    assert payload["sub"] == "7"
    assert payload["admin"] is True
    assert decode_access_token("garbage") is None


def test_api_key_hash():
    raw, prefix, key_hash = generate_api_key()
    assert raw.startswith("kgl_")
    assert raw[:8] == prefix
    assert hash_api_key(raw) == key_hash


def test_signup_login_and_quota():
    from app.db.database import init_db

    init_db()
    from fastapi.testclient import TestClient

    from app.api.main import app

    c = TestClient(app)
    email = f"user_{uuid.uuid4().hex[:8]}@test.com"

    r = c.post("/api/v1/auth/signup", json={"email": email, "password": "pw1234"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == email
    assert me["tier"] == "free"
    assert me["daily_quota"] > 0

    # duplicate signup blocked
    assert c.post("/api/v1/auth/signup", json={"email": email, "password": "pw1234"}).status_code == 409
    # bad login
    assert c.post("/api/v1/auth/login", json={"email": email, "password": "nope"}).status_code == 401


def test_admin_seeded_and_metrics_guarded():
    from app.db.database import init_db

    init_db()
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.config import get_settings

    c = TestClient(app)
    s = get_settings()
    # anonymous cannot read admin metrics
    assert c.get("/api/v1/admin/metrics").status_code == 403
    # admin can
    login = c.post("/api/v1/auth/login", json={"email": s.admin_email, "password": s.admin_password})
    assert login.status_code == 200
    tok = login.json()["access_token"]
    assert login.json()["is_admin"] is True
    m = c.get("/api/v1/admin/metrics", headers={"Authorization": f"Bearer {tok}"})
    assert m.status_code == 200
    assert "latency_ms" in m.json()
