"""Jurisdiction Mapper (PRD §4.2).

For a legal query, maps applicable jurisdiction: Central vs State law, Supreme Court
vs High Court precedent level, and any state-specific variations to watch for.
"""
from __future__ import annotations

import re

from app.retrieval.hybrid import retrieve

# subjects that are typically State or Concurrent List in India
_STATE_SUBJECTS = ["land", "tenancy", "shops", "establishment", "police", "agriculture",
                   "liquor", "stamp duty", "rent", "panchayat"]
_CONCURRENT_SUBJECTS = ["contract", "criminal", "labour", "education", "marriage", "bankruptcy",
                        "electricity", "forest"]


def map_jurisdiction(query: str) -> dict:
    low = query.lower()

    # Central vs State classification
    if any(s in low for s in _STATE_SUBJECTS):
        legislative = "State / Concurrent List — expect state-specific statutes and variations."
        level = "STATE"
    elif any(s in low for s in _CONCURRENT_SUBJECTS):
        legislative = "Concurrent List — Central law applies, but states may have amendments."
        level = "CONCURRENT"
    else:
        legislative = "Likely Central / Union List — uniform across India."
        level = "CENTRAL"

    # precedent level from retrieved cases
    _, _, fused = retrieve(query, top_k=8)
    courts = [c.metadata.get("court", "") for c in fused if c.metadata.get("court")]
    has_sc = any("supreme" in (c or "").lower() for c in courts)
    has_hc = any("high court" in (c or "").lower() for c in courts)
    if has_sc:
        precedent = "Supreme Court precedent governs and binds all courts in India."
    elif has_hc:
        precedent = "High Court precedent applies; binding within the state, persuasive elsewhere."
    else:
        precedent = "No binding precedent retrieved; rely on the statute text."

    variations = []
    if level in {"STATE", "CONCURRENT"}:
        variations.append(
            "Check state amendments / rules (e.g., state Shops & Establishment Acts, state CrPC amendments)."
        )

    return {
        "query": query,
        "legislative_competence": level,
        "legislative_note": legislative,
        "precedent_level": "SUPREME_COURT" if has_sc else ("HIGH_COURT" if has_hc else "NONE"),
        "precedent_note": precedent,
        "state_specific_variations": variations,
        "relevant_nodes": [c.source_node_id for c in fused[:5] if c.source_node_id],
    }
