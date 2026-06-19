"""In-memory NetworkX graph store — the offline fallback for Neo4j.

Implements a small, pragmatic subset of "Cypher-like" querying good enough for the
seed corpus: it understands the few-shot patterns our NL->Cypher chain emits, and
otherwise degrades to keyword node search.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional

import networkx as nx

from app.schemas import GraphNode


class MemoryGraphStore:
    backend = "networkx"

    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()

    # ---- mutations ----
    def upsert_node(self, node_id: str, labels: List[str], properties: dict[str, Any]) -> None:
        self.g.add_node(node_id, labels=list(labels), properties=dict(properties))

    def upsert_edge(self, edge_type: str, from_id: str, to_id: str, properties: Optional[dict] = None) -> None:
        for nid in (from_id, to_id):
            if nid not in self.g:
                self.g.add_node(nid, labels=[], properties={})
        self.g.add_edge(from_id, to_id, key=edge_type, type=edge_type, properties=properties or {})

    def clear(self) -> None:
        self.g.clear()

    # ---- reads ----
    def node_exists(self, node_id: str) -> bool:
        return node_id in self.g

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        if node_id not in self.g:
            return None
        data = self.g.nodes[node_id]
        return GraphNode(node_id=node_id, labels=data.get("labels", []), properties=data.get("properties", {}))

    def _to_node(self, node_id: str) -> GraphNode:
        data = self.g.nodes[node_id]
        return GraphNode(node_id=node_id, labels=data.get("labels", []), properties=data.get("properties", {}))

    def search_nodes(self, term: str, limit: int = 10) -> List[GraphNode]:
        term_l = term.lower()
        # extract bare section/article numbers from the query, e.g. "302", "66A"
        nums = set(re.findall(r"\b(\d+[a-z]?)\b", term_l))
        scored: list[tuple[float, str]] = []
        for nid, data in self.g.nodes(data=True):
            props = data.get("properties", {})
            hay = " ".join(str(v) for v in props.values()).lower() + " " + nid.lower()
            score = 0.0
            if props.get("number") and str(props["number"]).lower() in nums:
                score += 5.0
            for tok in re.findall(r"[a-z]+", term_l):
                if len(tok) > 2 and tok in hay:
                    score += 1.0
            if score > 0:
                scored.append((score, nid))
        scored.sort(reverse=True)
        return [self._to_node(nid) for _, nid in scored[:limit]]

    def neighbors(self, node_id: str, edge_types: Optional[List[str]] = None, depth: int = 1) -> List[GraphNode]:
        if node_id not in self.g:
            return []
        seen: set[str] = set()
        frontier = {node_id}
        for _ in range(max(1, depth)):
            nxt: set[str] = set()
            for nid in frontier:
                for _, tgt, key in self.g.out_edges(nid, keys=True):
                    if edge_types and key not in edge_types:
                        continue
                    if tgt not in seen:
                        nxt.add(tgt)
                for src, _, key in self.g.in_edges(nid, keys=True):
                    if edge_types and key not in edge_types:
                        continue
                    if src not in seen:
                        nxt.add(src)
            nxt -= {node_id}
            seen |= nxt
            frontier = nxt
        return [self._to_node(nid) for nid in seen if nid in self.g]

    def run_cypher(self, cypher: str, params: Optional[dict] = None) -> List[GraphNode]:
        """Best-effort interpretation of the limited Cypher our chain emits.

        Recognised shapes:
          - MATCH ... WHERE n.number = '302' ...           -> number lookup
          - MATCH (s)-[:CITED_IN|INTERPRETED_BY]->(c) ...  -> relationship hop
          - free text                                      -> keyword search
        """
        params = params or {}
        text = cypher.replace("\n", " ")

        # number / property equality lookup
        m = re.search(r"\.(number|act_id|name)\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            key, val = m.group(1), m.group(2)
            hits = [
                self._to_node(nid)
                for nid, data in self.g.nodes(data=True)
                if str(data.get("properties", {}).get(key, "")).lower() == val.lower()
            ]
            if hits:
                # also pull their immediate neighbours for multi-hop context
                expanded = list(hits)
                for h in hits:
                    expanded.extend(self.neighbors(h.node_id, depth=1))
                return _dedup(expanded)

        # relationship-type hop
        rels = re.findall(r"\[:?\s*([A-Z_|]+)\s*\]", text)
        if rels:
            edge_types = [t for chunk in rels for t in chunk.split("|") if t]
            # anchor on any number / keyword present
            anchors = self.search_nodes(text, limit=3)
            out: list[GraphNode] = []
            for a in anchors:
                out.append(a)
                out.extend(self.neighbors(a.node_id, edge_types=edge_types, depth=2))
            if out:
                return _dedup(out)

        # fallback: keyword search over the whole query string
        return self.search_nodes(params.get("query", text), limit=10)

    def stats(self) -> dict[str, int]:
        return {"nodes": self.g.number_of_nodes(), "edges": self.g.number_of_edges()}


def _dedup(nodes: List[GraphNode]) -> List[GraphNode]:
    seen: set[str] = set()
    out: List[GraphNode] = []
    for n in nodes:
        if n.node_id not in seen:
            seen.add(n.node_id)
            out.append(n)
    return out
