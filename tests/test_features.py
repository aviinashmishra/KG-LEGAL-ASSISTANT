import pytest

from app.bootstrap import initialize


@pytest.fixture(scope="module", autouse=True)
def _init():
    initialize(include_pdfs=False, verbose=False)


def test_outcome_predictor_distribution():
    from app.features.outcome_predictor import predict_outcome

    r = predict_outcome("murder with sudden provocation", offence_section="302", desired_outcome="acquittal")
    assert r["similar_cases_found"] > 0
    assert abs(sum(r["outcome_distribution"].values()) - 1.0) < 0.01
    assert 0.0 <= r["precedent_strength_score"] <= 1.0
    assert r["strength_label"] in {"STRONG", "MODERATE", "WEAK"}


def test_clause_risk_levels():
    from app.features.clause_risk import score_clauses

    text = "The employee shall not compete for 24 months post termination.\n\nConfidential information shall remain secret."
    r = score_clauses(text)
    assert r["clauses_scored"] >= 2
    assert r["overall_risk"] in {"LOW", "MEDIUM", "HIGH"}
    # the non-compete clause should be HIGH risk
    assert any(c["risk_level"] == "HIGH" for c in r["clauses"])


def test_jurisdiction_mapper():
    from app.features.jurisdiction import map_jurisdiction

    r = map_jurisdiction("Is a shops and establishment registration mandatory?")
    assert r["legislative_competence"] in {"STATE", "CONCURRENT", "CENTRAL"}
    assert "precedent_level" in r


def test_contract_drafter_has_clauses_with_basis():
    from app.features.contract_drafter import draft_contract

    r = draft_contract("employment", ["Acme Pvt Ltd", "Mr. Sharma"], "6-month probation")
    assert r["draft_markdown"].startswith("#")
    assert len(r["clauses"]) >= 4
    assert all("risk_level" in c for c in r["clauses"])


def test_contradiction_detector_flags_noncompete():
    from app.features.contradiction import detect_contradictions

    r = detect_contradictions("The employee agrees to a 12-month non-compete after termination.")
    assert r["clauses_analyzed"] >= 1
    assert r["conflicts_found"] >= 1
