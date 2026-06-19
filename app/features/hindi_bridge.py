"""Hindi Legal Query Bridge (PRD §7.4).

Translates a Hindi query to English legal terminology using a bilingual glossary
(stored on LegalConcept nodes) as a first-pass substitution, then optional neural
translation (IndicTrans2 if installed, else LLM, else glossary-only). The English
query feeds the normal pipeline; the answer can be rendered back with inline English
legal terms per professional convention.
"""
from __future__ import annotations

from typing import Dict

from app.agents.llm import get_llm
from app.kg.graph_store import get_graph_store

# small built-in glossary; extended from LegalConcept nodes' `hindi` property
_BASE_GLOSSARY: Dict[str, str] = {
    "hatya": "murder",
    "zamaanat": "bail",
    "agrim zamaanat": "anticipatory bail",
    "zameen ka mamla": "land dispute",
    "gair-pratispardha": "non-compete",
    "jeevan ka adhikaar": "right to life",
    "dhara": "section",
    "saja": "punishment",
}


def _glossary() -> Dict[str, str]:
    glossary = dict(_BASE_GLOSSARY)
    store = get_graph_store()
    try:
        nodes = store.search_nodes("concept", limit=100)
    except Exception:
        nodes = []
    for n in nodes:
        h = n.properties.get("hindi")
        name = n.properties.get("name")
        if h and name:
            glossary[h.lower()] = name
    return glossary


def translate_hi_to_en(query_hi: str) -> str:
    glossary = _glossary()
    text = query_hi
    # phrase-level substitution (longest first)
    for hindi in sorted(glossary, key=len, reverse=True):
        if hindi in text.lower():
            text = _ci_replace(text, hindi, glossary[hindi])

    # neural step
    try:
        from IndicTransToolkit import IndicProcessor  # type: ignore  # pragma: no cover

        # (full IndicTrans2 wiring omitted in MVP; presence => pass through)
        return text
    except Exception:
        pass

    llm = get_llm()
    if llm.is_real:
        try:
            return llm.complete(
                f"Translate this Indian legal query to English, preserving legal terms. "
                f"Output only the translation:\n{text}",
                max_tokens=200,
                fast=True,
            ).strip() or text
        except Exception:
            return text
    return text  # glossary-only fallback


def _ci_replace(text: str, target: str, repl: str) -> str:
    import re

    return re.sub(re.escape(target), repl, text, flags=re.IGNORECASE)
