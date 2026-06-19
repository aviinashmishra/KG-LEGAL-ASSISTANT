"""GraphStore interface + provider selection.

Both the Neo4j and the in-memory NetworkX implementations expose the same surface
so the rest of the system never knows which one is live.
"""
from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable

from app.config import get_settings
from app.schemas import GraphNode


@runtime_checkable
class GraphStore(Protocol):
    backend: str

    def upsert_node(self, node_id: str, labels: List[str], properties: dict[str, Any]) -> None: ...

    def upsert_edge(self, edge_type: str, from_id: str, to_id: str, properties: Optional[dict] = None) -> None: ...

    def node_exists(self, node_id: str) -> bool: ...

    def get_node(self, node_id: str) -> Optional[GraphNode]: ...

    def search_nodes(self, term: str, limit: int = 10) -> List[GraphNode]: ...

    def neighbors(self, node_id: str, edge_types: Optional[List[str]] = None, depth: int = 1) -> List[GraphNode]: ...

    def run_cypher(self, cypher: str, params: Optional[dict] = None) -> List[GraphNode]: ...

    def stats(self) -> dict[str, int]: ...

    def clear(self) -> None: ...


_STORE: Optional[GraphStore] = None


def get_graph_store(force_new: bool = False) -> GraphStore:
    """Return a singleton graph store, choosing Neo4j when configured."""
    global _STORE
    if _STORE is not None and not force_new:
        return _STORE

    settings = get_settings()
    if settings.use_neo4j:
        try:
            from app.kg.neo4j_store import Neo4jStore

            _STORE = Neo4jStore()
            return _STORE
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[graph_store] Neo4j unavailable ({exc}); falling back to in-memory.")

    from app.kg.memory_store import MemoryGraphStore

    _STORE = MemoryGraphStore()
    return _STORE
