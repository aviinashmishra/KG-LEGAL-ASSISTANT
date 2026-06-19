"""Golden ground-truth question set (sampled from PRD §8.2).

Each item lists the node ids we expect the retriever/citation layer to surface.
"""
from __future__ import annotations

GOLDEN_SET = [
    # --- basic statute lookup ---
    {
        "category": "statute_lookup",
        "question": "What is the punishment under Section 302 IPC?",
        "expected_nodes": ["node_ipc_302"],
    },
    {
        "category": "statute_lookup",
        "question": "What does Section 420 IPC deal with?",
        "expected_nodes": ["node_ipc_420"],
    },
    {
        "category": "statute_lookup",
        "question": "What is anticipatory bail under Section 438 CrPC?",
        "expected_nodes": ["node_crpc_438"],
    },
    # --- multi-hop reasoning ---
    {
        "category": "multi_hop",
        "question": "Can anticipatory bail be granted for a Section 302 offence?",
        "expected_nodes": ["node_ipc_302", "node_crpc_438", "node_crpc_437"],
    },
    {
        "category": "multi_hop",
        "question": "Which case overruled the position in Bachan Singh on mandatory death penalty?",
        "expected_nodes": ["case_mithu_punjab", "case_bachan_singh"],
    },
    # --- amendment history ---
    {
        "category": "amendment_history",
        "question": "What changed in CrPC Section 41 after 2009?",
        "expected_nodes": ["node_crpc_41", "amend_crpc_41_2009"],
    },
    {
        "category": "amendment_history",
        "question": "What happened to Section 66A of the IT Act?",
        "expected_nodes": ["node_it_66a", "case_shreya_singhal"],
    },
    # --- case strategy ---
    {
        "category": "case_strategy",
        "question": "What factors influence anticipatory bail decisions?",
        "expected_nodes": ["node_crpc_438", "case_siddharam"],
    },
    # --- contract compliance ---
    {
        "category": "contract_compliance",
        "question": "Is a 12-month non-compete clause enforceable in India?",
        "expected_nodes": ["node_contract_27"],
    },
    {
        "category": "constitutional",
        "question": "How did Maneka Gandhi expand Article 21?",
        "expected_nodes": ["node_const_21", "case_maneka_gandhi"],
    },
]
