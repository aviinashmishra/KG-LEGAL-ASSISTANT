"""Feature router: all Phase-3 WOW features (PRD §7 / §4.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.deps import Principal, enforce_quota
from app.bootstrap import ensure_initialized
from app.schemas import (
    ClauseRiskRequest,
    ContradictionRequest,
    DraftRequest,
    HindiRequest,
    JurisdictionRequest,
    OutcomeRequest,
    TimelineRequest,
)

router = APIRouter(prefix="/api/v1/features", tags=["features"])


@router.post("/contradiction")
def contradiction(req: ContradictionRequest, _: Principal = Depends(enforce_quota)) -> dict:
    from app.features.contradiction import detect_contradictions

    ensure_initialized()
    return detect_contradictions(req.document_a, req.document_b)


@router.post("/timeline")
def timeline(req: TimelineRequest, _: Principal = Depends(enforce_quota)) -> dict:
    from app.features.temporal import legal_timeline

    ensure_initialized()
    return legal_timeline(req.section_number, req.as_of_date)


@router.post("/outcome")
def outcome(req: OutcomeRequest, _: Principal = Depends(enforce_quota)) -> dict:
    from app.features.outcome_predictor import predict_outcome

    ensure_initialized()
    return predict_outcome(req.facts, req.offence_section, req.desired_outcome)


@router.post("/clause-risk")
def clause_risk(req: ClauseRiskRequest, _: Principal = Depends(enforce_quota)) -> dict:
    from app.features.clause_risk import score_clauses

    ensure_initialized()
    return score_clauses(req.contract_text)


@router.post("/jurisdiction")
def jurisdiction(req: JurisdictionRequest, _: Principal = Depends(enforce_quota)) -> dict:
    from app.features.jurisdiction import map_jurisdiction

    ensure_initialized()
    return map_jurisdiction(req.query)


@router.post("/draft")
def draft(req: DraftRequest, _: Principal = Depends(enforce_quota)) -> dict:
    from app.features.contract_drafter import draft_contract

    ensure_initialized()
    return draft_contract(req.contract_type, req.parties, req.key_terms)


@router.post("/hindi")
def hindi(req: HindiRequest, _: Principal = Depends(enforce_quota)) -> dict:
    from app.features.hindi_bridge import translate_hi_to_en
    from app.services.chat_service import answer_query

    ensure_initialized()
    english = translate_hi_to_en(req.query_hi)
    resp = answer_query(english, language="hi")
    return {"original_hi": req.query_hi, "translated_en": english, "answer": resp.model_dump()}
