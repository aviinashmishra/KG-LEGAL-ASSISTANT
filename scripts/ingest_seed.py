"""Build the knowledge graph + retrieval indexes from seed data (and data/pdfs/).

Usage:
    python scripts/ingest_seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# allow running as a plain script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import initialize  # noqa: E402


def main() -> None:
    summary = initialize(include_pdfs=True, verbose=True)
    g = summary["graph"]
    print("\n=== Ingestion complete ===")
    print(f"  Graph nodes : {g.get('nodes')}")
    print(f"  Graph edges : {g.get('edges')}")
    print(f"  Indexed docs: {summary['index'].get('documents')}")
    print(f"  PDFs ingested: {summary['pdfs'].get('files')}")
    if summary["warnings"]:
        print(f"  Warnings    : {summary['warnings']}")


if __name__ == "__main__":
    main()
