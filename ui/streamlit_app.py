"""Streamlit demo UI (PRD §4.2 Reasoning Audit Trail UI).

Run with:  streamlit run ui/streamlit_app.py

Features:
  - query box with streamed agent progress
  - IRAC answer + verified citations + confidence
  - PyVis visualization of the knowledge-graph nodes traversed
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app.agents.graph import run_pipeline_streaming, state_to_response  # noqa: E402
from app.bootstrap import initialize  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.kg.graph_store import get_graph_store  # noqa: E402

st.set_page_config(page_title="KG-RAG Legal Assistant", page_icon="⚖️", layout="wide")


@st.cache_resource
def _bootstrap():
    return initialize(verbose=False)


def render_graph(node_ids: list[str]) -> str | None:
    try:
        from pyvis.network import Network
    except Exception:
        return None
    store = get_graph_store()
    net = Network(height="450px", width="100%", directed=True, bgcolor="#ffffff")
    added = set()
    for nid in node_ids:
        node = store.get_node(nid)
        if not node:
            continue
        label = node.properties.get("number") or node.properties.get("name") or nid
        title = node.properties.get("title") or node.properties.get("name") or nid
        color = {"Section": "#1f77b4", "Case": "#d62728", "LegalConcept": "#2ca02c",
                 "Amendment": "#9467bd", "Act": "#ff7f0e"}.get(
            node.labels[0] if node.labels else "", "#7f7f7f"
        )
        net.add_node(nid, label=str(label), title=str(title), color=color)
        added.add(nid)
    # draw edges among traversed nodes
    for nid in list(added):
        for nb in store.neighbors(nid, depth=1):
            if nb.node_id in added:
                net.add_edge(nid, nb.node_id)
    tmp = Path(tempfile.gettempdir()) / "kg_legal_graph.html"
    net.save_graph(str(tmp))
    return tmp.read_text(encoding="utf-8")


def main() -> None:
    _bootstrap()
    settings = get_settings()
    store = get_graph_store()

    st.title("⚖️ KG-RAG Legal Assistant")
    st.caption("Knowledge-Graph-powered, citation-grounded legal reasoning for Indian law")

    with st.sidebar:
        st.subheader("Providers")
        st.code(settings.provider_banner())
        st.subheader("Graph")
        st.json(store.stats())
        st.subheader("Try")
        st.write(
            "- What is the punishment under Section 302 IPC?\n"
            "- Can anticipatory bail be granted for Section 302?\n"
            "- What changed in CrPC Section 41 after 2009?\n"
            "- Is a 12-month non-compete clause enforceable in India?"
        )

    query = st.text_input("Ask a legal question", value="Can anticipatory bail be granted for Section 302 IPC?")
    if not st.button("Run", type="primary"):
        return

    progress = st.empty()
    final_state = None
    steps = []
    with st.status("Running multi-agent pipeline...", expanded=True) as status:
        for event_name, state in run_pipeline_streaming(query):
            final_state = state
            trace = state.get("trace", [])
            if trace:
                steps.append(trace[-1])
                progress.write("\n".join(f"• {s}" for s in steps))
        status.update(label="Pipeline complete", state="complete")

    if final_state is None:
        st.error("No result produced.")
        return

    resp = state_to_response(final_state)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("Answer")
        badge = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(resp.confidence, "")
        st.markdown(f"**Confidence:** {badge} {resp.confidence}  |  "
                    f"**Hallucination score:** {resp.hallucination_score:.2f}")
        st.markdown(resp.answer)

        if resp.citations:
            st.subheader("Citations")
            for c in resp.citations:
                mark = "✅" if c.verified else "⚠️"
                st.markdown(f"{mark} {c.display}  ·  `{c.kg_node or 'unverified'}`")

    with col2:
        st.subheader("Knowledge Graph traversal")
        html = render_graph(resp.kg_nodes_traversed)
        if html:
            st.components.v1.html(html, height=470)
        else:
            st.info("Install pyvis to see the graph visualization.")
            st.write(resp.kg_nodes_traversed)

    with st.expander("Full agent trace"):
        for line in resp.trace:
            st.write(f"• {line}")
    if resp.irac:
        with st.expander("IRAC structured output (JSON)"):
            st.json(resp.irac.model_dump())


if __name__ == "__main__":
    main()
