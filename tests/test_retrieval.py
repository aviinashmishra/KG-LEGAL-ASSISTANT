from app.retrieval.fusion import reciprocal_rank_fusion
from app.schemas import Document, GraphNode


def test_rrf_merges_and_dedups():
    kg = [GraphNode(node_id="node_ipc_302", labels=["Section"], properties={"number": "302", "title": "Murder"})]
    dense = [
        Document(doc_id="node_ipc_302", text="punishment for murder", source_node_id="node_ipc_302"),
        Document(doc_id="node_crpc_437", text="bail provisions", source_node_id="node_crpc_437"),
    ]
    bm25 = [Document(doc_id="node_ipc_302", text="section 302", source_node_id="node_ipc_302")]

    fused = reciprocal_rank_fusion(kg, dense, bm25)
    ids = [c.source_node_id for c in fused]
    # node appearing in all three paths must rank first and not be duplicated
    assert ids[0] == "node_ipc_302"
    assert ids.count("node_ipc_302") == 1
    top = fused[0]
    assert set(top.origin) == {"kg", "dense", "bm25"}


def test_rrf_orders_by_score():
    dense = [Document(doc_id="a", text="a", source_node_id="a"),
             Document(doc_id="b", text="b", source_node_id="b")]
    fused = reciprocal_rank_fusion([], dense, [])
    assert fused[0].rrf_score >= fused[1].rrf_score
