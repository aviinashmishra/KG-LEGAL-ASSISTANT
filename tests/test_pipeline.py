"""End-to-end smoke test running on the local fallback providers."""
import pytest

from app.agents.graph import run_pipeline, state_to_response
from app.bootstrap import initialize


@pytest.fixture(scope="module", autouse=True)
def _init():
    initialize(include_pdfs=False, verbose=False)


def test_statute_lookup_is_grounded():
    state = run_pipeline("What is the punishment under Section 302 IPC?")
    resp = state_to_response(state)
    assert resp.answer
    # the IPC 302 node should have been traversed and cited
    assert "node_ipc_302" in resp.kg_nodes_traversed
    assert any(c.verified for c in resp.citations)
    assert resp.hallucination_score <= 0.5


def test_multi_hop_bail_query():
    state = run_pipeline("Can anticipatory bail be granted for Section 302 IPC?")
    resp = state_to_response(state)
    traversed = set(resp.kg_nodes_traversed)
    # should touch both the offence and a bail provision
    assert "node_ipc_302" in traversed
    assert traversed & {"node_crpc_438", "node_crpc_437"}


def test_response_has_irac_structure():
    state = run_pipeline("Is a 12-month non-compete clause enforceable in India?")
    resp = state_to_response(state)
    assert resp.irac is not None
    assert resp.irac.issue
    assert resp.confidence in {"HIGH", "MEDIUM", "LOW"}
