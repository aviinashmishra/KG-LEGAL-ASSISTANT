"""Temporal Legal Timeline + 'law as of date X' (PRD §7.2).

Walks SUPERSEDES edges from Amendment nodes to a Section to reconstruct the
amendment history and resolve the applicable text at a given date.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.kg.graph_store import get_graph_store
from app.schemas import GraphNode


def _find_section(number: str) -> Optional[GraphNode]:
    store = get_graph_store()
    for n in store.search_nodes(number, limit=20):
        if "Section" in n.labels and str(n.properties.get("number", "")).lower() == number.lower():
            return n
    return None


def legal_timeline(section_number: str, as_of_date: Optional[str] = None) -> dict:
    store = get_graph_store()
    section = _find_section(section_number)
    if not section:
        return {"section": section_number, "found": False, "events": []}

    # amendments are connected via SUPERSEDES(Amendment -> Section)
    related = store.neighbors(section.node_id, edge_types=["SUPERSEDES"], depth=1)
    amendments = [n for n in related if "Amendment" in n.labels]

    events = []
    for amd in sorted(amendments, key=lambda n: str(n.properties.get("effective_date", ""))):
        p = amd.properties
        events.append(
            {
                "amendment_id": amd.node_id,
                "effective_date": p.get("effective_date"),
                "year": p.get("year"),
                "change_type": p.get("change_type"),
                "trigger_event": p.get("trigger_event"),
                "old_text": p.get("old_text"),
                "new_text": p.get("new_text"),
            }
        )

    applicable_text = section.properties.get("text", "")
    if as_of_date:
        cutoff = _parse_date(as_of_date)
        applied = [e for e in events if e.get("effective_date") and _parse_date(e["effective_date"]) <= cutoff]
        if applied:
            applicable_text = applied[-1].get("new_text") or applicable_text
        else:
            applicable_text = section.properties.get("text", "")

    return {
        "section": section_number,
        "found": True,
        "node_id": section.node_id,
        "title": section.properties.get("title"),
        "current_text": section.properties.get("text"),
        "as_of_date": as_of_date,
        "applicable_text_as_of_date": applicable_text,
        "events": events,
    }


def _parse_date(value: str) -> date:
    try:
        y, m, d = (int(x) for x in str(value).split("-")[:3])
        return date(y, m, d)
    except Exception:
        return date(1900, 1, 1)
