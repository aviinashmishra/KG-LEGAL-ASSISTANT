"""Three-path hybrid retrieval orchestrator (PRD §4.1).

dense (vector) + Cypher graph traversal (multi-hop) + BM25 sparse  ->  RRF  ->  rerank
"""
from __future__ import annotations

from typing import List, Tuple

from app.config import get_settings
from app.kg.cypher_chain import retrieve_from_kg
from app.kg.graph_store import GraphStore, get_graph_store
from app.retrieval.bm25 import get_bm25_index
from app.retrieval.fusion import reciprocal_rank_fusion, rerank
from app.retrieval.vector_store import get_vector_store
from app.schemas import Document, GraphNode, RankedChunk


def retrieve(
    query: str,
    store: GraphStore | None = None,
    top_k: int | None = None,
) -> Tuple[List[GraphNode], List[Document], List[RankedChunk]]:
    """Run all three retrieval paths and return (kg_nodes, vector_docs, fused_chunks)."""
    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k
    store = store or get_graph_store()

    # path 1: KG (Cypher + correction loop)
    kg_nodes = retrieve_from_kg(store, query)

    # path 2: dense vectors
    dense_docs = get_vector_store().search(query, top_k=10)

    # path 3: sparse BM25
    bm25_docs = get_bm25_index().search(query, top_k=10)

    # fuse + rerank
    fused = reciprocal_rank_fusion(kg_nodes, dense_docs, bm25_docs)
    reranked = rerank(query, fused, top_k=top_k)
    return kg_nodes, dense_docs, reranked
