"""Clause Risk Scorer (PRD §4.2).

Assigns a LOW/MEDIUM/HIGH litigation-risk score to each clause of a contract using
KG pattern matching against relevant provisions plus an LLM (or heuristic) judgment.
"""
from __future__ import annotations

import re
from typing import List

from app.agents.llm import get_llm
from app.retrieval.hybrid import retrieve

# heuristic risk signals for the offline path
_HIGH_RISK = [
    (r"(non[- ]?compete|not\s+(?:to\s+)?compete|restrain\w*\s+\w*\s*trade)",
     "Post-employment non-compete / restraint clauses are generally void under Section 27, Contract Act."),
    (r"unlimited liabilit", "Unlimited liability clauses are frequently litigated and may be unconscionable."),
    (r"waiv\w* .*(statutory|mandatory)", "Waiver of statutory rights is typically unenforceable."),
    (r"penalt\w+", "Penalty (vs liquidated damages) clauses attract Section 74 scrutiny."),
    (r"perpetu\w+", "Perpetual obligations are often read down by courts."),
]
_MED_RISK = [
    (r"indemnif", "Indemnity scope should be bounded; broad indemnities invite disputes."),
    (r"terminat", "Termination terms should specify notice and cure periods."),
    (r"confidential", "Confidentiality terms should define duration and carve-outs."),
    (r"arbitrat", "Arbitration clause should fix seat, rules, and number of arbitrators."),
]


def split_clauses(text: str) -> List[str]:
    raw = re.split(r"(?:\n{2,})|(?:\d+\.\s)|(?:;\s)", text)
    return [c.strip() for c in raw if len(c.strip()) > 15]


def score_clauses(contract_text: str) -> dict:
    clauses = split_clauses(contract_text)
    llm = get_llm()
    results = []
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}

    for clause in clauses[:40]:
        _, _, fused = retrieve(clause, top_k=3)
        legal_basis = fused[0] if fused else None
        if llm.is_real:
            risk = _llm_score(llm, clause, legal_basis.text if legal_basis else "")
        else:
            risk = _heuristic_score(clause)
        counts[risk["level"]] = counts.get(risk["level"], 0) + 1
        results.append(
            {
                "clause": clause[:300],
                "risk_level": risk["level"],
                "rationale": risk["rationale"],
                "legal_basis_node": legal_basis.source_node_id if legal_basis else None,
            }
        )

    overall = "HIGH" if counts["HIGH"] else ("MEDIUM" if counts["MEDIUM"] else "LOW")
    return {
        "clauses_scored": len(results),
        "distribution": counts,
        "overall_risk": overall,
        "clauses": results,
    }


def _heuristic_score(clause: str) -> dict:
    low = clause.lower()
    for pat, why in _HIGH_RISK:
        if re.search(pat, low):
            return {"level": "HIGH", "rationale": why}
    for pat, why in _MED_RISK:
        if re.search(pat, low):
            return {"level": "MEDIUM", "rationale": why}
    return {"level": "LOW", "rationale": "No high-risk pattern detected against the knowledge base."}


def _llm_score(llm, clause: str, basis: str) -> dict:
    import json

    prompt = (
        "Rate the litigation risk of this contract clause under Indian law as LOW, MEDIUM, or HIGH. "
        'Output strict JSON: {"level": "LOW|MEDIUM|HIGH", "rationale": str}.\n'
        f"CLAUSE: {clause}\nRELEVANT LAW: {basis}"
    )
    try:
        raw = llm.complete(prompt, max_tokens=200, fast=True)
        s, e = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[s : e + 1])
        if data.get("level") in {"LOW", "MEDIUM", "HIGH"}:
            return data
    except Exception:
        pass
    return _heuristic_score(clause)
