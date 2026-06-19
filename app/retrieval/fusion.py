"""Reciprocal Rank Fusion + reranking (PRD §4.1 Hybrid Retrieval Engine).

RRF combines the ranked lists from the KG, dense, and BM25 paths. Cohere Rerank is
applied as a final step when COHERE_API_KEY is set; otherwise the fused RRF order
is kept (rerank_score mirrors rrf_score).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from app.config import get_settings
from app.schemas import Document, GraphNode, RankedChunk

RRF_K = 60


def _node_to_doc(node: GraphNode) -> Document:
    return Document(
        doc_id=node.node_id,
        text=node.as_text(),
        source_node_id=node.node_id,
        metadata={**node.properties, "labels": node.labels},
    )


def reciprocal_rank_fusion(
    kg_results: List[GraphNode],
    dense_results: List[Document],
    bm25_results: List[Document],
) -> List[RankedChunk]:
    """Fuse three ranked lists into a single deduplicated RankedChunk list."""
    contributions: Dict[str, Dict] = {}

    def add(items: List[Document], origin: str) -> None:
        for rank, doc in enumerate(items):
            key = doc.source_node_id or doc.doc_id
            entry = contributions.setdefault(
                key, {"doc": doc, "score": 0.0, "origin": set()}
            )
            entry["score"] += 1.0 / (RRF_K + rank + 1)
            entry["origin"].add(origin)
            # prefer the richest text/metadata seen for this key
            if len(doc.text) > len(entry["doc"].text):
                entry["doc"] = doc

    add([_node_to_doc(n) for n in kg_results], "kg")
    add(dense_results, "dense")
    add(bm25_results, "bm25")

    fused: List[RankedChunk] = []
    for entry in contributions.values():
        doc = entry["doc"]
        fused.append(
            RankedChunk(
                doc_id=doc.doc_id,
                text=doc.text,
                source_node_id=doc.source_node_id,
                metadata=doc.metadata,
                rrf_score=entry["score"],
                rerank_score=entry["score"],
                origin=sorted(entry["origin"]),
            )
        )
    fused.sort(key=lambda c: -c.rrf_score)
    return fused


def rerank(query: str, chunks: List[RankedChunk], top_k: int = 8) -> List[RankedChunk]:
    settings = get_settings()
    if settings.use_cohere and chunks:
        try:
            import cohere

            client = cohere.Client(api_key=settings.cohere_api_key)
            resp = client.rerank(
                model=settings.cohere_rerank_model,
                query=query,
                documents=[c.text for c in chunks],
                top_n=min(top_k, len(chunks)),
            )
            out: List[RankedChunk] = []
            for r in resp.results:
                ch = chunks[r.index].model_copy(update={"rerank_score": float(r.relevance_score)})
                out.append(ch)
            return out
        except Exception as exc:  # pragma: no cover
            print(f"[fusion] Cohere rerank unavailable ({exc}); keeping RRF order.")
    return chunks[:top_k]
