"""Evaluation runner (PRD §8.1).

Computes retrieval recall and citation-grounding rate against the golden set using
local metrics that always run. If `ragas` is installed and an LLM key is present,
RAGAS faithfulness/relevancy can additionally be computed.
"""
from __future__ import annotations

from typing import List

from app.agents.graph import run_pipeline
from app.bootstrap import ensure_initialized
from app.eval.golden_dataset import GOLDEN_SET
from app.retrieval.hybrid import retrieve


def evaluate(top_k: int = 8) -> dict:
    ensure_initialized()
    recall_hits = 0
    recall_total = 0
    grounding_rates: List[float] = []
    per_question = []

    for item in GOLDEN_SET:
        q = item["question"]
        expected = set(item["expected_nodes"])

        # --- retrieval recall ---
        kg_nodes, _, fused = retrieve(q, top_k=top_k)
        retrieved_ids = {c.source_node_id for c in fused if c.source_node_id}
        retrieved_ids |= {n.node_id for n in kg_nodes}
        hit = len(expected & retrieved_ids)
        recall_hits += hit
        recall_total += len(expected)
        recall = hit / len(expected) if expected else 0.0

        # --- citation grounding (end-to-end) ---
        state = run_pipeline(q)
        cites = state.get("verified_citations", [])
        grounded = sum(1 for c in cites if c.verified)
        grounding = grounded / len(cites) if cites else 0.0
        grounding_rates.append(grounding)

        per_question.append(
            {
                "question": q,
                "category": item["category"],
                "recall": round(recall, 2),
                "citation_grounding": round(grounding, 2),
                "hallucination_score": state.get("hallucination_score", 0.0),
                "confidence": state.get("confidence"),
            }
        )

    summary = {
        "n_questions": len(GOLDEN_SET),
        "retrieval_recall": round(recall_hits / recall_total, 3) if recall_total else 0.0,
        "avg_citation_grounding": round(sum(grounding_rates) / len(grounding_rates), 3)
        if grounding_rates
        else 0.0,
        "targets": {"retrieval_recall": ">0.80", "citation_grounding": ">0.95"},
    }
    return {"summary": summary, "per_question": per_question}


if __name__ == "__main__":
    import json

    print(json.dumps(evaluate(), indent=2))
