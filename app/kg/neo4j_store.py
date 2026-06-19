"""Neo4j AuraDB graph store (PRD §3.2). Active when NEO4J_* env vars are set."""
from __future__ import annotations

from typing import Any, List, Optional

from app.config import get_settings
from app.schemas import GraphNode


class Neo4jStore:
    backend = "neo4j"

    def __init__(self) -> None:
        from neo4j import GraphDatabase  # imported lazily so the dep is optional

        s = get_settings()
        self._db = s.neo4j_database
        self._driver = GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_username, s.neo4j_password)
        )
        self._driver.verify_connectivity()

    def close(self) -> None:
        self._driver.close()

    # ---- mutations ----
    def upsert_node(self, node_id: str, labels: List[str], properties: dict[str, Any]) -> None:
        label_str = ":".join(labels) if labels else "Entity"
        props = {**properties, "node_id": node_id}
        cypher = (
            f"MERGE (n:{label_str} {{node_id: $node_id}}) SET n += $props"
        )
        with self._driver.session(database=self._db) as session:
            session.run(cypher, node_id=node_id, props=props)

    def upsert_edge(self, edge_type: str, from_id: str, to_id: str, properties: Optional[dict] = None) -> None:
        cypher = (
            "MATCH (a {node_id: $from_id}) MATCH (b {node_id: $to_id}) "
            f"MERGE (a)-[r:{edge_type}]->(b) SET r += $props"
        )
        with self._driver.session(database=self._db) as session:
            session.run(cypher, from_id=from_id, to_id=to_id, props=properties or {})

    def clear(self) -> None:
        with self._driver.session(database=self._db) as session:
            session.run("MATCH (n) DETACH DELETE n")

    # ---- reads ----
    def node_exists(self, node_id: str) -> bool:
        with self._driver.session(database=self._db) as session:
            rec = session.run(
                "MATCH (n {node_id: $id}) RETURN count(n) AS c", id=node_id
            ).single()
            return bool(rec and rec["c"] > 0)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        with self._driver.session(database=self._db) as session:
            rec = session.run(
                "MATCH (n {node_id: $id}) RETURN n, labels(n) AS labels", id=node_id
            ).single()
            return _record_to_node(rec) if rec else None

    def search_nodes(self, term: str, limit: int = 10) -> List[GraphNode]:
        cypher = (
            "MATCH (n) WHERE toLower(coalesce(n.title,'') + ' ' + coalesce(n.name,'') "
            "+ ' ' + coalesce(n.text,'') + ' ' + coalesce(n.number,'')) CONTAINS toLower($term) "
            "RETURN n, labels(n) AS labels LIMIT $limit"
        )
        return self._collect(cypher, {"term": term, "limit": limit})

    def neighbors(self, node_id: str, edge_types: Optional[List[str]] = None, depth: int = 1) -> List[GraphNode]:
        rel = ""
        if edge_types:
            rel = ":" + "|".join(edge_types)
        cypher = (
            f"MATCH (n {{node_id: $id}})-[{rel}*1..{max(1, depth)}]-(m) "
            "RETURN DISTINCT m AS n, labels(m) AS labels LIMIT 50"
        )
        return self._collect(cypher, {"id": node_id})

    def run_cypher(self, cypher: str, params: Optional[dict] = None) -> List[GraphNode]:
        return self._collect(cypher, params or {})

    def stats(self) -> dict[str, int]:
        with self._driver.session(database=self._db) as session:
            n = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            e = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            return {"nodes": int(n), "edges": int(e)}

    # ---- helpers ----
    def _collect(self, cypher: str, params: dict) -> List[GraphNode]:
        with self._driver.session(database=self._db) as session:
            out: List[GraphNode] = []
            for rec in session.run(cypher, **params):
                node = _record_to_node(rec)
                if node:
                    out.append(node)
            return out


def _record_to_node(rec) -> Optional[GraphNode]:
    if rec is None:
        return None
    node = rec.get("n")
    if node is None:
        return None
    props = dict(node)
    labels = rec.get("labels") or list(getattr(node, "labels", []))
    node_id = props.get("node_id") or str(getattr(node, "element_id", ""))
    return GraphNode(node_id=node_id, labels=list(labels), properties=props)
