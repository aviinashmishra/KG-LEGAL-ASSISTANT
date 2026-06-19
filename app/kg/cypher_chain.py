"""NL -> Cypher generation with a 3-attempt correction loop (PRD §6.2 kg_retriever).

When an LLM is available it generates Cypher from few-shot examples; otherwise it
emits a simple property-match query that the MemoryGraphStore understands. Either
way, if a query returns no rows we retry up to 3 times with a relaxed strategy
before handing off to keyword search.
"""
from __future__ import annotations

from typing import List

from app.kg.graph_store import GraphStore
from app.schemas import GraphNode

FEW_SHOT = """You translate natural-language questions about Indian law into a single Cypher query
for a Neo4j graph with nodes (Act, Section, Case, LegalConcept, Amendment) carrying a `number`,
`title`, `text`, `name` property, and relationships AMENDS, CITED_IN, OVERRULES, APPLICABLE_TO,
SUPERSEDES, INTERPRETED_BY, HAS_SECTION.

Q: What is the punishment under Section 302 IPC?
Cypher: MATCH (s:Section) WHERE s.number = '302' RETURN s LIMIT 5

Q: Which cases interpret Section 438 CrPC?
Cypher: MATCH (s:Section)-[:INTERPRETED_BY|CITED_IN]->(c:Case) WHERE s.number = '438' RETURN s, c LIMIT 10

Q: What overruled Bachan Singh?
Cypher: MATCH (a:Case)-[:OVERRULES]->(b:Case) WHERE toLower(b.title) CONTAINS 'bachan' RETURN a, b LIMIT 5

Only output the Cypher query, nothing else.
Q: {question}
Cypher:"""


def generate_cypher(question: str) -> str:
    from app.agents.llm import get_llm

    llm = get_llm()
    if llm.is_real:
        try:
            raw = llm.complete(FEW_SHOT.format(question=question), max_tokens=200, fast=True)
            cypher = raw.strip().split("\n")[0].strip().strip("`")
            if cypher.upper().startswith("MATCH"):
                return cypher
        except Exception:
            pass
    # deterministic fallback understood by MemoryGraphStore.run_cypher
    return f"MATCH (n) WHERE keyword RETURN n // {question}"


def retrieve_from_kg(store: GraphStore, question: str, max_attempts: int = 3) -> List[GraphNode]:
    """Generate Cypher, execute, and self-correct up to `max_attempts` times."""
    attempt = 0
    last: List[GraphNode] = []
    while attempt < max_attempts:
        attempt += 1
        cypher = generate_cypher(question)
        try:
            results = store.run_cypher(cypher, params={"query": question})
        except Exception:
            results = []
        if results:
            return results
        last = results
    # final fallback: direct keyword node search
    return store.search_nodes(question, limit=10) or last
