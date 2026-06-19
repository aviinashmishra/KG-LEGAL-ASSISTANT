"""Knowledge graph layer (PRD §3.1 Layer 1, §5.2 schema)."""

from app.kg.graph_store import GraphStore, get_graph_store

__all__ = ["GraphStore", "get_graph_store"]
