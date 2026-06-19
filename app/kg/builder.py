"""Knowledge Graph Auto-Builder (PRD §4.1).

Two ingestion paths:
  1. load_seed()            -> deterministic load of curated seed JSON.
  2. ingest_parsed_doc()    -> LLM structured-JSON entity extraction from parsed
                               legal text, with graph-integrity validation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import SEED_DIR
from app.kg.graph_store import GraphStore
from app.parsing.pdf_parser import ParsedDocument

# Map seed collections -> node label
_LABELS = {
    "acts": "Act",
    "sections": "Section",
    "cases": "Case",
    "concepts": "LegalConcept",
    "amendments": "Amendment",
    "parties": "Party",
}
_ID_KEYS = {
    "acts": "act_id",
    "sections": "section_id",
    "cases": "case_id",
    "concepts": "concept_id",
    "amendments": "amendment_id",
    "parties": "party_id",
}


def load_seed(store: GraphStore, seed_path: Path | None = None) -> dict[str, int]:
    """Populate the graph store from the curated seed JSON."""
    seed_path = seed_path or (SEED_DIR / "legal_seed.json")
    data = json.loads(Path(seed_path).read_text(encoding="utf-8"))

    counts = {"nodes": 0, "edges": 0}
    for collection, label in _LABELS.items():
        id_key = _ID_KEYS[collection]
        for item in data.get(collection, []):
            node_id = item[id_key]
            store.upsert_node(node_id, [label], item)
            counts["nodes"] += 1

    for edge in data.get("edges", []):
        store.upsert_edge(edge["type"], edge["from"], edge["to"], edge.get("properties"))
        counts["edges"] += 1

    return counts


# --------------------------------------------------------------------------- #
# LLM extraction path
# --------------------------------------------------------------------------- #
_EXTRACT_PROMPT = """You are a legal knowledge-graph extractor for Indian law.
Given the text of a statute, extract entities and relationships as strict JSON with this schema:
{{
  "act": {{"act_id": "act_<slug>", "title": str, "year": int}},
  "sections": [{{"section_id": "node_<slug>", "number": str, "title": str, "text": str,
                 "concepts": [str]}}],
  "concepts": [{{"concept_id": "concept_<slug>", "name": str, "definition": str}}],
  "edges": [{{"type": "APPLICABLE_TO", "from": "node_<slug>", "to": "concept_<slug>"}}]
}}
Use lowercase underscore slugs. Only output JSON. Text:
---
{text}
---"""


def ingest_parsed_doc(store: GraphStore, doc: ParsedDocument, act_year: int = 0) -> dict[str, int]:
    """Ingest a parsed document. Uses the LLM extractor when available, else a
    deterministic mapping from the parsed structure."""
    from app.agents.llm import get_llm

    llm = get_llm()
    counts = {"nodes": 0, "edges": 0}

    if llm.is_real:
        extracted = _llm_extract(llm, doc)
        if extracted:
            return _ingest_extracted(store, extracted)

    # deterministic fallback: build directly from the parsed hierarchy
    act_slug = _slug(doc.title)
    act_id = f"act_{act_slug}"
    store.upsert_node(act_id, ["Act"], {"act_id": act_id, "title": doc.title, "year": act_year})
    counts["nodes"] += 1
    for sec in doc.sections:
        sid = f"node_{act_slug}_{sec.number.lower()}"
        store.upsert_node(
            sid,
            ["Section"],
            {
                "section_id": sid,
                "act_id": act_id,
                "number": sec.number,
                "title": sec.title,
                "text": sec.full_text(),
            },
        )
        store.upsert_edge("HAS_SECTION", act_id, sid)
        counts["nodes"] += 1
        counts["edges"] += 1
    return counts


def _llm_extract(llm, doc: ParsedDocument) -> dict[str, Any] | None:
    body = "\n\n".join(s.full_text() for s in doc.sections[:30])
    try:
        raw = llm.complete(_EXTRACT_PROMPT.format(text=body[:12000]), max_tokens=3000)
        return _safe_json(raw)
    except Exception:
        return None


def _ingest_extracted(store: GraphStore, data: dict[str, Any]) -> dict[str, int]:
    counts = {"nodes": 0, "edges": 0}
    act = data.get("act")
    if act and act.get("act_id"):
        store.upsert_node(act["act_id"], ["Act"], act)
        counts["nodes"] += 1
    for sec in data.get("sections", []):
        if sec.get("section_id"):
            store.upsert_node(sec["section_id"], ["Section"], sec)
            counts["nodes"] += 1
            if act and act.get("act_id"):
                store.upsert_edge("HAS_SECTION", act["act_id"], sec["section_id"])
                counts["edges"] += 1
    for c in data.get("concepts", []):
        if c.get("concept_id"):
            store.upsert_node(c["concept_id"], ["LegalConcept"], c)
            counts["nodes"] += 1
    for e in data.get("edges", []):
        if e.get("from") and e.get("to"):
            store.upsert_edge(e.get("type", "RELATED"), e["from"], e["to"])
            counts["edges"] += 1
    return counts


def validate_integrity(store: GraphStore) -> list[str]:
    """Lightweight graph-integrity check; returns a list of warnings."""
    warnings: list[str] = []
    stats = store.stats()
    if stats.get("nodes", 0) == 0:
        warnings.append("graph has no nodes")
    return warnings


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


def _safe_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
