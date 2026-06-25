"""Graph router: serves knowledge-graph topology for the 3D luxury viewer.

Read-only, unauthenticated visualization endpoints. Returns nodes + typed edges
in a shape the Three.js `3d-force-graph` front-end consumes directly:

    { "nodes": [{id, label, type, val, title, props}],
      "links": [{source, target, type}] }
"""
from __future__ import annotations

from typing import Iterable

from fastapi import APIRouter
from pydantic import BaseModel

from app.bootstrap import ensure_initialized
from app.kg.graph_store import get_graph_store

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])

# size hint (3D node radius) by node type — Acts are hubs, concepts small
_TYPE_VAL = {"Act": 10, "Section": 6, "Case": 7, "LegalConcept": 4, "Amendment": 5}


def _node_payload(node) -> dict:
    props = node.properties or {}
    node_type = node.labels[0] if node.labels else "Unknown"
    label = (
        props.get("number")
        and f"§{props['number']}"
        or props.get("title")
        or props.get("name")
        or node.node_id
    )
    title = props.get("title") or props.get("name") or node.node_id
    return {
        "id": node.node_id,
        "label": str(label),
        "title": str(title),
        "type": node_type,
        "val": _TYPE_VAL.get(node_type, 5),
        "props": {
            k: props.get(k)
            for k in ("number", "act_id", "year", "court", "outcome", "text", "definition", "summary")
            if props.get(k)
        },
    }


def _links_among(store, ids: set[str]) -> list[dict]:
    """Collect typed edges whose endpoints are both inside `ids` (in-memory store)."""
    g = getattr(store, "g", None)
    links: list[dict] = []
    if g is None:
        # Neo4j / other backend: approximate via neighbour reads
        for nid in ids:
            for nb in store.neighbors(nid, depth=1):
                if nb.node_id in ids:
                    links.append({"source": nid, "target": nb.node_id, "type": "RELATED"})
        return _dedup_links(links)
    for src, tgt, key in g.edges(keys=True):
        if src in ids and tgt in ids:
            links.append({"source": src, "target": tgt, "type": str(key)})
    return _dedup_links(links)


def _dedup_links(links: Iterable[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for l in links:
        sig = (l["source"], l["target"], l["type"])
        if sig not in seen:
            seen.add(sig)
            out.append(l)
    return out


class SubgraphRequest(BaseModel):
    node_ids: list[str] = []
    expand: int = 1  # extra hops of context to pull in around the traversed nodes


@router.post("/subgraph")
def subgraph(req: SubgraphRequest) -> dict:
    """Induced subgraph around the traversed nodes (+ `expand` hops of context)."""
    ensure_initialized()
    store = get_graph_store()
    ids: set[str] = set()
    for nid in req.node_ids:
        if store.node_exists(nid):
            ids.add(nid)
            for nb in store.neighbors(nid, depth=max(0, req.expand)):
                ids.add(nb.node_id)
    nodes = [_node_payload(store.get_node(nid)) for nid in ids if store.get_node(nid)]
    # mark the originally-traversed (anchor) nodes so the UI can highlight them
    anchors = set(req.node_ids)
    for n in nodes:
        n["anchor"] = n["id"] in anchors
    return {"nodes": nodes, "links": _links_among(store, {n["id"] for n in nodes})}


@router.get("/full")
def full_graph(limit: int = 400) -> dict:
    """The entire knowledge graph (capped) — powers the Explorer galaxy view."""
    ensure_initialized()
    store = get_graph_store()
    g = getattr(store, "g", None)
    if g is None:
        return {"nodes": [], "links": [], "stats": store.stats()}
    ids = list(g.nodes())[:limit]
    id_set = set(ids)
    nodes = [_node_payload(store.get_node(nid)) for nid in ids if store.get_node(nid)]
    return {
        "nodes": nodes,
        "links": _links_among(store, id_set),
        "stats": store.stats(),
    }
