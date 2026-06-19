"""Case Outcome Predictor / precedent-strength analysis (PRD §7.3).

Framed deliberately as 'precedent strength', NOT a guaranteed prediction. Retrieves
similar historical cases from the KG + vector search, computes an outcome
distribution, surfaces the top differentiating factors, and reports a strength score.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional

from app.kg.graph_store import GraphStore, get_graph_store
from app.retrieval.hybrid import retrieve

_DESIRED_BY_OUTCOME = {
    "conviction": "acquittal",
    "acquittal": "acquittal",
    "bail granted": "bail granted",
    "bail denied": "bail granted",
}


def _all_cases(store: GraphStore) -> List[dict]:
    cases = []
    if getattr(store, "backend", "") == "networkx":
        for nid, data in store.g.nodes(data=True):  # type: ignore[attr-defined]
            if "Case" in data.get("labels", []):
                cases.append({"node_id": nid, **data.get("properties", {})})
    else:
        for n in store.run_cypher("MATCH (n:Case) RETURN n, labels(n) AS labels"):
            cases.append({"node_id": n.node_id, **n.properties})
    return cases


def predict_outcome(
    facts: str,
    offence_section: Optional[str] = None,
    desired_outcome: Optional[str] = None,
    k: int = 8,
) -> dict:
    store = get_graph_store()

    # infer offence section from facts if not provided
    if not offence_section:
        m = re.search(r"\b(\d{2,3}[A-Z]?)\b", facts)
        offence_section = m.group(1) if m else None

    all_cases = _all_cases(store)
    pool = [c for c in all_cases if c.get("offence_section")]
    if offence_section:
        matched = [c for c in pool if str(c.get("offence_section")) == str(offence_section)]
    else:
        matched = pool

    # rank by vector similarity to the facts (best-effort)
    _, _, fused = retrieve(facts, top_k=20)
    sim_rank = {c.source_node_id: i for i, c in enumerate(fused) if c.source_node_id}
    matched.sort(key=lambda c: sim_rank.get(c["node_id"], 999))
    similar = matched[:k]

    if not similar:
        return {
            "offence_section": offence_section,
            "similar_cases_found": 0,
            "message": "No comparable historical cases in the knowledge graph for this offence.",
            "disclaimer": _DISCLAIMER,
        }

    outcomes = Counter(c.get("outcome", "unknown") for c in similar)
    total = sum(outcomes.values())
    distribution = {k_: round(v / total, 2) for k_, v in outcomes.items()}

    # differentiating factors associated with each outcome
    factor_by_outcome: dict[str, Counter] = {}
    for c in similar:
        factor_by_outcome.setdefault(c.get("outcome", "unknown"), Counter()).update(c.get("factors", []))
    top_factors = {
        out: [f for f, _ in cnt.most_common(3)] for out, cnt in factor_by_outcome.items()
    }

    desired = desired_outcome or _DESIRED_BY_OUTCOME.get(
        outcomes.most_common(1)[0][0], outcomes.most_common(1)[0][0]
    )
    strength = round(distribution.get(desired, 0.0), 2)

    return {
        "offence_section": offence_section,
        "similar_cases_found": total,
        "outcome_distribution": distribution,
        "desired_outcome": desired,
        "precedent_strength_score": strength,
        "strength_label": _label(strength),
        "top_factors_by_outcome": top_factors,
        "top_cases": [
            {
                "node_id": c["node_id"],
                "title": c.get("title"),
                "year": c.get("year"),
                "outcome": c.get("outcome"),
                "factors": c.get("factors", []),
            }
            for c in similar[:3]
        ],
        "disclaimer": _DISCLAIMER,
    }


def _label(score: float) -> str:
    if score >= 0.66:
        return "STRONG"
    if score >= 0.4:
        return "MODERATE"
    return "WEAK"


_DISCLAIMER = (
    "Precedent strength analysis is probabilistic and educational only. It is NOT legal "
    "advice or a guaranteed prediction of any case outcome."
)
