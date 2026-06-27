"""One-shot initialization: load the graph + build retrieval indexes.

Called at API / UI startup and by the ingestion script. Idempotent for the
in-memory backends; for Neo4j/Qdrant it upserts (safe to re-run).
"""
from __future__ import annotations

import threading

from app.config import PDF_DIR, get_settings
from app.kg.builder import ingest_parsed_doc, load_seed, validate_integrity
from app.kg.graph_store import get_graph_store
from app.parsing.pdf_parser import parse_file
from app.retrieval.indexer import build_indexes

_INITIALIZED = False
_LAST_SUMMARY: dict = {}
_INIT_LOCK = threading.Lock()


def initialize(include_pdfs: bool = True, verbose: bool = True) -> dict:
    """Load seed data (+ any drop-in PDFs) and build the dense/sparse indexes.

    Thread-safe and idempotent: concurrent callers (e.g. the background warm-up
    started at app startup and the first request) won't double-build.
    """
    global _INITIALIZED, _LAST_SUMMARY
    with _INIT_LOCK:
        if _INITIALIZED:
            return _LAST_SUMMARY
        summary = _do_initialize(include_pdfs=include_pdfs, verbose=verbose)
        _LAST_SUMMARY = summary
        _INITIALIZED = True
        return summary


def _do_initialize(include_pdfs: bool = True, verbose: bool = True) -> dict:
    settings = get_settings()
    store = get_graph_store()

    if verbose:
        print(settings.provider_banner())

    seed_counts = load_seed(store)

    pdf_counts = {"nodes": 0, "edges": 0, "files": 0}
    if include_pdfs and PDF_DIR.exists():
        for pdf in sorted(PDF_DIR.glob("*.pdf")) + sorted(PDF_DIR.glob("*.txt")):
            try:
                doc = parse_file(pdf)
                c = ingest_parsed_doc(store, doc)
                pdf_counts["nodes"] += c["nodes"]
                pdf_counts["edges"] += c["edges"]
                pdf_counts["files"] += 1
            except Exception as exc:  # pragma: no cover
                print(f"[bootstrap] failed to ingest {pdf.name}: {exc}")

    index_counts = build_indexes(store)
    warnings = validate_integrity(store)

    summary = {
        "graph": store.stats(),
        "seed": seed_counts,
        "pdfs": pdf_counts,
        "index": index_counts,
        "warnings": warnings,
    }
    if verbose:
        print(f"[bootstrap] {summary}")
    return summary


def ensure_initialized() -> None:
    if not _INITIALIZED:
        initialize(verbose=True)
