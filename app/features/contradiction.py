"""Legal Contradiction Detector (PRD §7.1).

Parses two documents into clauses, retrieves the most relevant statutory provision
for each clause from the KG, and flags conflicts. With an LLM available, conflict
classification uses a chain-of-thought CONFLICT_CHECK prompt; otherwise a heuristic
keyword/antonym check provides a basic conflict signal.
"""
from __future__ import annotations

import re
from typing import List

from app.agents.llm import get_llm
from app.retrieval.hybrid import retrieve

_CONFLICT_PROMPT = """You are an Indian legal compliance analyst. Determine whether CLAUSE A conflicts
with PROVISION B. Think step by step, then output STRICT JSON:
{{"conflict": true|false, "conflict_type": "direct"|"indirect"|"ambiguity"|"none",
  "remedy": str, "confidence": "HIGH"|"MEDIUM"|"LOW", "explanation": str}}

CLAUSE A: {clause}
PROVISION B (statute): {provision}
"""

# crude antonym/limit signals for the heuristic fallback
_RISK_TERMS = [
    ("non-compete", "void", "restraint of trade"),
    ("12-month", "void", "two year"),
    ("waive", "mandatory", "cannot be waived"),
    ("unlimited liability", "limited", "cap"),
]


def split_clauses(text: str) -> List[str]:
    raw = re.split(r"(?:\n{2,})|(?:\d+\.\s)|(?:;\s)", text)
    return [c.strip() for c in raw if len(c.strip()) > 25]


def detect_contradictions(document_a: str, document_b: str = "") -> dict:
    clauses = split_clauses(document_a)
    llm = get_llm()
    conflicts: List[dict] = []

    for clause in clauses[:20]:
        # find the most relevant statutory provision (from KG/corpus, or doc B)
        _, _, fused = retrieve(clause)
        provision = fused[0] if fused else None
        provision_text = provision.text if provision else document_b[:500]
        if not provision_text:
            continue

        if llm.is_real:
            result = _llm_conflict(llm, clause, provision_text)
        else:
            result = _heuristic_conflict(clause, provision_text)

        if result and result.get("conflict"):
            conflicts.append(
                {
                    "clause_a": clause,
                    "provision_b": provision_text[:400],
                    "provision_node": provision.source_node_id if provision else None,
                    **result,
                }
            )

    return {
        "clauses_analyzed": len(clauses),
        "conflicts_found": len(conflicts),
        "conflicts": conflicts,
    }


def _llm_conflict(llm, clause: str, provision: str) -> dict:
    import json

    try:
        raw = llm.complete(_CONFLICT_PROMPT.format(clause=clause, provision=provision), max_tokens=500)
        s, e = raw.find("{"), raw.rfind("}")
        return json.loads(raw[s : e + 1]) if s != -1 else {}
    except Exception:
        return {}


def _heuristic_conflict(clause: str, provision: str) -> dict:
    cl, pr = clause.lower(), provision.lower()
    for a, b, hint in _RISK_TERMS:
        if a in cl and (b in pr or hint in pr):
            return {
                "conflict": True,
                "conflict_type": "direct",
                "remedy": "Review clause against the cited provision; the clause may be unenforceable.",
                "confidence": "MEDIUM",
                "explanation": f"Clause mentions '{a}' while the provision indicates '{b}/{hint}'.",
            }
    return {"conflict": False, "conflict_type": "none", "confidence": "LOW", "explanation": ""}
