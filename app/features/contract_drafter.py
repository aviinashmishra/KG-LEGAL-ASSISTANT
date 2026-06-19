"""Smart Contract Drafter (PRD §4.2).

RAG-backed contract generation: retrieves applicable clauses/provisions from the KG,
drafts a compliant contract (LLM when available, else a structured template), and
tags every clause with its legal basis + a litigation-risk score (clause_risk).
"""
from __future__ import annotations

from typing import List, Optional

from app.agents.llm import get_llm
from app.features.clause_risk import _heuristic_score
from app.retrieval.hybrid import retrieve

_TEMPLATES = {
    "employment": [
        ("Appointment & Role", "The Employer appoints the Employee in the role and on the terms set out herein."),
        ("Compensation", "The Employee shall be paid the agreed remuneration, subject to applicable statutory deductions."),
        ("Confidentiality", "The Employee shall keep all proprietary information confidential during and after employment."),
        ("Non-Compete", "The Employee shall not engage in competing business during employment. (Post-employment restraints are void under Section 27, Contract Act.)"),
        ("Termination", "Either party may terminate on the agreed notice period; statutory dues shall be settled on exit."),
        ("Governing Law & Dispute Resolution", "This agreement is governed by the laws of India; disputes shall be resolved by arbitration seated in India."),
    ],
    "nda": [
        ("Definition of Confidential Information", "Confidential Information means non-public information disclosed by either party."),
        ("Obligations", "The Receiving Party shall use Confidential Information solely for the stated purpose."),
        ("Term", "Confidentiality obligations survive for the agreed duration after disclosure."),
        ("Governing Law", "Governed by the laws of India; courts at the agreed seat have jurisdiction."),
    ],
    "service": [
        ("Scope of Services", "The Service Provider shall render the services described in the Statement of Work."),
        ("Fees & Payment", "Fees are payable as per the agreed schedule; GST applies as per the GST Act 2017."),
        ("Indemnity", "Each party indemnifies the other against third-party claims arising from its breach."),
        ("Limitation of Liability", "Liability is limited to the fees paid in the preceding twelve months."),
        ("Governing Law & Dispute Resolution", "Governed by the laws of India; disputes via arbitration."),
    ],
}


def draft_contract(
    contract_type: str,
    parties: List[str],
    key_terms: Optional[str] = "",
) -> dict:
    ctype = (contract_type or "service").strip().lower()
    template = _TEMPLATES.get(ctype, _TEMPLATES["service"])
    party_line = " and ".join(parties) if parties else "the Parties"

    llm = get_llm()
    clauses = []
    for heading, default_text in template:
        # ground each clause in the KG
        _, _, fused = retrieve(f"{ctype} {heading} {key_terms}", top_k=3)
        basis = fused[0] if fused else None
        text = default_text
        if llm.is_real:
            text = _llm_clause(llm, ctype, heading, party_line, key_terms, basis.text if basis else "") or default_text
        risk = _heuristic_score(text)
        clauses.append(
            {
                "heading": heading,
                "text": text,
                "legal_basis_node": basis.source_node_id if basis else None,
                "legal_basis": (basis.metadata.get("title") if basis else None),
                "risk_level": risk["level"],
                "risk_rationale": risk["rationale"],
            }
        )

    draft_md = f"# {contract_type.title()} Agreement\n\n**Between:** {party_line}\n\n"
    for i, c in enumerate(clauses, 1):
        draft_md += f"## {i}. {c['heading']}\n{c['text']}\n\n"

    return {
        "contract_type": ctype,
        "parties": parties,
        "draft_markdown": draft_md,
        "clauses": clauses,
        "disclaimer": "Auto-generated draft for review by a qualified advocate; not legal advice.",
    }


def _llm_clause(llm, ctype, heading, parties, key_terms, basis) -> str:
    prompt = (
        f"Draft the '{heading}' clause for an Indian {ctype} agreement between {parties}. "
        f"Key terms: {key_terms or 'standard'}. Relevant law: {basis}. "
        "Output only the clause text, 1-3 sentences, compliant with Indian law."
    )
    try:
        return llm.complete(prompt, max_tokens=250).strip()
    except Exception:
        return ""
