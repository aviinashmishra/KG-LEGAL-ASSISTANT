"""The 7 specialized agent nodes (PRD §6.2).

Each node is a pure function (state) -> partial-state-update, suitable for a
LangGraph StateGraph. They are also directly callable for testing without LangGraph.
"""
from __future__ import annotations

import re
from typing import List

from app.agents.llm import get_llm
from app.config import get_settings
from app.kg.graph_store import get_graph_store
from app.retrieval.hybrid import retrieve
from app.schemas import (
    Citation,
    IRACSchema,
    LegalAgentState,
    RankedChunk,
)


def _log(state: LegalAgentState, msg: str) -> None:
    state.setdefault("trace", []).append(msg)


# --------------------------------------------------------------------------- #
# 1. query_planner
# --------------------------------------------------------------------------- #
_INTENT_KEYWORDS = {
    "drafting": ["draft", "write a", "generate", "clause", "agreement template"],
    "compliance": ["comply", "compliance", "enforceable", "violat", "permitted", "legal to"],
    "strategy": ["bail", "defend", "strategy", "chances", "likelihood", "argue"],
}


def query_planner(state: LegalAgentState) -> LegalAgentState:
    query = state["original_query"]
    _log(state, "Planning query and classifying intent...")

    intent = "research"
    low = query.lower()
    for cand, kws in _INTENT_KEYWORDS.items():
        if any(k in low for k in kws):
            intent = cand
            break

    # decompose into sub-questions (split on conjunctions / question marks)
    parts = [p.strip() for p in re.split(r"\?|\band\b|;", query) if len(p.strip()) > 8]
    sub_questions = parts[:4] if parts else [query]

    state["intent"] = intent  # type: ignore[typeddict-item]
    state["sub_questions"] = sub_questions
    _log(state, f"Intent={intent}; {len(sub_questions)} sub-question(s).")
    return state


# --------------------------------------------------------------------------- #
# 2. kg_retriever + 3. vector_retriever + 4. context_fusion
#    (run together via the hybrid orchestrator to share fusion)
# --------------------------------------------------------------------------- #
def retrieval_node(state: LegalAgentState) -> LegalAgentState:
    store = get_graph_store()
    _log(state, "Searching knowledge graph (Cypher) ...")
    all_kg = []
    all_fused: List[RankedChunk] = []
    seen: set[str] = set()

    for sub in state.get("sub_questions", [state["original_query"]]):
        kg_nodes, dense_docs, fused = retrieve(sub, store=store)
        all_kg.extend(kg_nodes)
        for ch in fused:
            key = ch.source_node_id or ch.doc_id
            if key not in seen:
                seen.add(key)
                all_fused.append(ch)

    _log(state, f"Found {len(all_kg)} graph node(s); fused to {len(all_fused)} context chunk(s).")
    all_fused.sort(key=lambda c: -max(c.rerank_score, c.rrf_score))
    top_k = get_settings().retrieval_top_k
    state["kg_results"] = _dedup_nodes(all_kg)
    state["fused_context"] = all_fused[:top_k]
    return state


# --------------------------------------------------------------------------- #
# 5. irac_reasoner
# --------------------------------------------------------------------------- #
def irac_reasoner(state: LegalAgentState) -> LegalAgentState:
    _log(state, "Applying IRAC legal reasoning ...")
    llm = get_llm()
    irac = llm.reason_irac(state["original_query"], state.get("fused_context", []))
    # ensure traversed nodes include the fused context source ids
    ctx_nodes = [c.source_node_id for c in state.get("fused_context", []) if c.source_node_id]
    irac.kg_nodes_traversed = _dedup(list(irac.kg_nodes_traversed) + ctx_nodes)
    state["irac_output"] = irac
    return state


# --------------------------------------------------------------------------- #
# 6. citation_verifier
# --------------------------------------------------------------------------- #
def citation_verifier(state: LegalAgentState) -> LegalAgentState:
    _log(state, "Verifying citations against the knowledge graph ...")
    store = get_graph_store()
    irac = state.get("irac_output")
    citations: List[Citation] = []
    total = 0
    unverified = 0

    if irac:
        for rule in irac.applicable_rules:
            total += 1
            node_id = rule.kg_node
            verified = bool(node_id and store.node_exists(node_id))
            if not verified:
                unverified += 1
            citations.append(
                Citation(
                    kg_node=node_id,
                    display=_format_citation(rule),
                    verified=verified,
                    confidence="HIGH" if verified else "LOW",
                )
            )

    score = (unverified / total) if total else 0.0
    state["verified_citations"] = citations
    state["hallucination_score"] = round(score, 3)
    if irac:
        irac.hallucination_score = round(score, 3)
    _log(state, f"{total - unverified}/{total} citations verified; hallucination_score={score:.2f}.")
    return state


# --------------------------------------------------------------------------- #
# 7. response_synthesizer
# --------------------------------------------------------------------------- #
def response_synthesizer(state: LegalAgentState) -> LegalAgentState:
    _log(state, "Synthesizing final response ...")
    irac = state.get("irac_output")
    citations = state.get("verified_citations", [])
    if not irac:
        state["final_answer"] = "No answer could be generated for this query."
        state["confidence"] = "LOW"
        return state

    verified_cites = [c for c in citations if c.verified]
    footnotes = "\n".join(f"  - {c.display}" for c in verified_cites) or "  (no verified citations)"

    answer = (
        f"**Issue.** {irac.issue}\n\n"
        f"**Rule.** "
        + "; ".join(_format_citation_for_rule(r) for r in irac.applicable_rules)
        + f"\n\n**Application.** {irac.application}\n\n"
        f"**Conclusion.** {irac.conclusion}\n\n"
        f"**Citations (verified against knowledge graph):**\n{footnotes}"
    )

    # overall confidence factors in citation grounding
    grounding = (len(verified_cites) / len(citations)) if citations else 0.0
    if grounding >= 0.8 and irac.confidence == "HIGH":
        confidence = "HIGH"
    elif grounding >= 0.5:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    state["final_answer"] = answer
    state["confidence"] = confidence  # type: ignore[typeddict-item]
    irac.confidence = confidence  # type: ignore[assignment]
    _log(state, f"Done. Overall confidence={confidence}.")
    return state


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def needs_rewrite(state: LegalAgentState) -> bool:
    settings = get_settings()
    score = state.get("hallucination_score", 0.0)
    rewrites = state.get("rewrite_count", 0)
    return score > settings.hallucination_max_unverified and rewrites < settings.max_rewrites


def increment_rewrite(state: LegalAgentState) -> LegalAgentState:
    state["rewrite_count"] = state.get("rewrite_count", 0) + 1
    _log(state, f"Hallucination guard triggered rewrite #{state['rewrite_count']}.")
    # drop unverified rules so the rewrite is forced onto grounded context
    irac = state.get("irac_output")
    if irac:
        store = get_graph_store()
        irac.applicable_rules = [
            r for r in irac.applicable_rules if r.kg_node and store.node_exists(r.kg_node)
        ]
    return state


def _format_citation(rule) -> str:
    if rule.case:
        bits = [rule.case]
        if rule.court:
            bits.append(rule.court)
        if rule.year:
            bits.append(str(rule.year))
        return "(" + ", ".join(bits) + ")"
    bits = []
    if rule.section:
        bits.append(f"Section {rule.section}")
    if rule.act:
        bits.append(str(rule.act))
    return "(" + ", ".join(bits) + ")" if bits else "(uncited)"


def _format_citation_for_rule(rule) -> str:
    return f"{rule.text} {_format_citation(rule)}".strip()


def _dedup(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _dedup_nodes(nodes):
    seen: set[str] = set()
    out = []
    for n in nodes:
        if n.node_id not in seen:
            seen.add(n.node_id)
            out.append(n)
    return out
