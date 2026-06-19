"""LangGraph StateGraph wiring the 7 agent nodes + hallucination rewrite loop.

Graph shape (PRD §6):

  query_planner -> retrieval -> irac_reasoner -> citation_verifier
        ^                                              |
        |                                       needs_rewrite?
        +------ increment_rewrite <---- yes -----------+
                                          no
                                           v
                                  response_synthesizer -> END

If `langgraph` is not importable, `run_pipeline` executes the same nodes in plain
Python so the system still works.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from app.agents import nodes
from app.schemas import LegalAgentState, QueryResponse


def _build_langgraph():
    from langgraph.graph import END, StateGraph

    g = StateGraph(LegalAgentState)
    g.add_node("query_planner", nodes.query_planner)
    g.add_node("retrieval", nodes.retrieval_node)
    g.add_node("irac_reasoner", nodes.irac_reasoner)
    g.add_node("citation_verifier", nodes.citation_verifier)
    g.add_node("increment_rewrite", nodes.increment_rewrite)
    g.add_node("response_synthesizer", nodes.response_synthesizer)

    g.set_entry_point("query_planner")
    g.add_edge("query_planner", "retrieval")
    g.add_edge("retrieval", "irac_reasoner")
    g.add_edge("irac_reasoner", "citation_verifier")
    g.add_conditional_edges(
        "citation_verifier",
        lambda s: "rewrite" if nodes.needs_rewrite(s) else "synthesize",
        {"rewrite": "increment_rewrite", "synthesize": "response_synthesizer"},
    )
    g.add_edge("increment_rewrite", "irac_reasoner")
    g.add_edge("response_synthesizer", END)
    return g.compile()


_COMPILED = None


def get_pipeline():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = _build_langgraph()
    return _COMPILED


def _initial_state(query: str, language: str = "en") -> LegalAgentState:
    return {
        "original_query": query,
        "language": language,
        "rewrite_count": 0,
        "trace": [],
    }


def run_pipeline(query: str, language: str = "en") -> LegalAgentState:
    """Run the full pipeline and return the final state."""
    state = _initial_state(query, language)
    try:
        pipeline = get_pipeline()
        result = pipeline.invoke(state)
        return result  # type: ignore[return-value]
    except Exception as exc:
        # plain-Python fallback (also covers environments without langgraph)
        print(f"[graph] LangGraph unavailable/failed ({exc}); running sequential fallback.")
        return _run_sequential(state)


def _run_sequential(state: LegalAgentState) -> LegalAgentState:
    nodes.query_planner(state)
    nodes.retrieval_node(state)
    while True:
        nodes.irac_reasoner(state)
        nodes.citation_verifier(state)
        if nodes.needs_rewrite(state):
            nodes.increment_rewrite(state)
            continue
        break
    nodes.response_synthesizer(state)
    return state


def run_pipeline_streaming(query: str, language: str = "en") -> Iterable[tuple[str, LegalAgentState]]:
    """Yield (event, state) after each node so the API can stream progress.

    Uses the sequential runner for deterministic, fine-grained streaming events.
    """
    state = _initial_state(query, language)
    step_fns: list[tuple[str, Callable[[LegalAgentState], LegalAgentState]]] = [
        ("query_planner", nodes.query_planner),
        ("retrieval", nodes.retrieval_node),
    ]
    for name, fn in step_fns:
        fn(state)
        yield name, state

    while True:
        nodes.irac_reasoner(state)
        yield "irac_reasoner", state
        nodes.citation_verifier(state)
        yield "citation_verifier", state
        if nodes.needs_rewrite(state):
            nodes.increment_rewrite(state)
            yield "increment_rewrite", state
            continue
        break

    nodes.response_synthesizer(state)
    yield "response_synthesizer", state


def state_to_response(state: LegalAgentState) -> QueryResponse:
    irac = state.get("irac_output")
    return QueryResponse(
        answer=state.get("final_answer", ""),
        confidence=state.get("confidence", "LOW"),
        irac=irac,
        citations=state.get("verified_citations", []),
        hallucination_score=state.get("hallucination_score", 0.0),
        kg_nodes_traversed=irac.kg_nodes_traversed if irac else [],
        trace=state.get("trace", []),
    )
