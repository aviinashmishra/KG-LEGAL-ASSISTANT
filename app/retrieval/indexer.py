"""Build the dense + sparse indexes from the knowledge-graph nodes.

Each Section / Case / LegalConcept node becomes a retrievable Document whose
`source_node_id` ties it back to the graph for citation verification.
"""
from __future__ import annotations

from typing import List

from app.kg.graph_store import GraphStore
from app.retrieval.bm25 import get_bm25_index
from app.retrieval.vector_store import get_vector_store
from app.schemas import Document, GraphNode

_INDEXABLE = {"Section", "Case", "LegalConcept", "Amendment"}


def nodes_to_documents(nodes: List[GraphNode]) -> List[Document]:
    docs: List[Document] = []
    for n in nodes:
        if not (set(n.labels) & _INDEXABLE):
            continue
        props = n.properties
        text = _node_text(n)
        docs.append(
            Document(
                doc_id=n.node_id,
                text=text,
                source_node_id=n.node_id,
                metadata={
                    "labels": n.labels,
                    "number": props.get("number"),
                    "title": props.get("title") or props.get("name"),
                    "act": props.get("act_id"),
                    "act_title": props.get("act"),
                    "year": props.get("year"),
                    "court": props.get("court"),
                },
            )
        )
    return docs


def _node_text(n: GraphNode) -> str:
    p = n.properties
    head = p.get("title") or p.get("name") or n.node_id
    body = p.get("text") or p.get("summary") or p.get("definition") or ""
    extras = []
    for key in ("number", "act", "year", "court", "outcome", "explanation", "proviso"):
        if p.get(key):
            extras.append(f"{key}: {p[key]}")
    return f"{head}. {body} " + " ".join(extras)


def all_graph_nodes(store: GraphStore) -> List[GraphNode]:
    """Pull every indexable node out of the store (works for both backends)."""
    # MemoryGraphStore: iterate the networkx graph directly.
    if getattr(store, "backend", "") == "networkx":
        out: List[GraphNode] = []
        for nid, data in store.g.nodes(data=True):  # type: ignore[attr-defined]
            out.append(
                GraphNode(node_id=nid, labels=data.get("labels", []), properties=data.get("properties", {}))
            )
        return out
    # Neo4j: query for all indexable labels.
    label_list = ", ".join(f"'{lbl}'" for lbl in _INDEXABLE)
    return store.run_cypher(
        f"MATCH (n) WHERE any(l IN labels(n) WHERE l IN [{label_list}]) "
        "RETURN n, labels(n) AS labels"
    )


def build_indexes(store: GraphStore) -> dict[str, int]:
    nodes = all_graph_nodes(store)
    docs = nodes_to_documents(nodes)
    get_vector_store(force_new=True).upsert(docs)
    get_bm25_index().build(docs)
    return {"documents": len(docs)}
