import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.database import init_db


@pytest.fixture(scope="module", autouse=True)
def _init():
    init_db()


@pytest.fixture()
def client():
    return TestClient(app)


def _auth(client):
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "pw1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_ready_and_health(client):
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready").json()
    assert ready["ready"] is True
    assert ready["graph_stats"]["nodes"] > 0


def test_anonymous_query_works(client):
    r = client.post("/api/v1/chat/query", json={"query": "What is the punishment under Section 302 IPC?"})
    assert r.status_code == 200
    body = r.json()
    assert "node_ipc_302" in body["kg_nodes_traversed"]
    assert body["confidence"] in {"HIGH", "MEDIUM", "LOW"}


def test_authed_query_persists_history(client):
    headers = _auth(client)
    r = client.post("/api/v1/chat/query", json={"query": "Can anticipatory bail be granted for Section 302?"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["conversation_id"] is not None

    convs = client.get("/api/v1/chat/conversations", headers=headers).json()
    assert len(convs) >= 1
    msgs = client.get(f"/api/v1/chat/conversations/{convs[0]['id']}", headers=headers).json()
    assert any(m["role"] == "assistant" for m in msgs)


def test_feature_endpoints(client):
    assert client.post("/api/v1/features/outcome", json={"facts": "murder sudden fight", "offence_section": "302"}).status_code == 200
    assert client.post("/api/v1/features/clause-risk", json={"contract_text": "Non-compete for 24 months."}).status_code == 200
    assert client.post("/api/v1/features/jurisdiction", json={"query": "land dispute"}).status_code == 200
    d = client.post("/api/v1/features/draft", json={"contract_type": "nda", "parties": ["A", "B"]})
    assert d.status_code == 200 and d.json()["clauses"]


def test_billing_plans_and_upgrade(client):
    headers = _auth(client)
    plans = client.get("/api/v1/billing/plans").json()
    assert {p["tier"] for p in plans} == {"free", "pro", "enterprise"}
    up = client.post("/api/v1/billing/checkout", json={"tier": "pro"}, headers=headers)
    assert up.status_code == 200 and up.json()["tier"] == "pro"
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["tier"] == "pro"
