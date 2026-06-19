"""Validate .env credentials by actually connecting to each provider.

Usage:  python scripts/check_env.py
Prints OK / FAIL per provider so you can confirm keys before launching the server.
Makes tiny (cheap) live calls for LLM/embeddings.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

OK = "  [OK]  "
FAIL = " [FAIL] "
SKIP = " [skip] "


def line(tag, name, detail=""):
    print(f"{tag}{name:<26}{detail}")


def main() -> None:
    s = get_settings()
    print("=" * 64)
    print(" KG-RAG Legal Assistant — environment check")
    print("=" * 64)

    # ---- Anthropic ----
    if s.use_anthropic:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=s.anthropic_api_key)
            msg = client.messages.create(
                model=s.anthropic_fast_model, max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            line(OK, "Anthropic (Claude)", f"model={s.anthropic_fast_model}")
        except Exception as e:
            line(FAIL, "Anthropic (Claude)", str(e)[:90])
    else:
        line(SKIP, "Anthropic (Claude)", "no key -> stub LLM")

    # ---- OpenAI ----
    if s.use_openai_embeddings:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=s.openai_api_key)
            r = client.embeddings.create(model=s.openai_embed_model, input="ping")
            line(OK, "OpenAI (embeddings)", f"dim={len(r.data[0].embedding)}")
        except Exception as e:
            line(FAIL, "OpenAI (embeddings)", str(e)[:90])
    else:
        line(SKIP, "OpenAI (embeddings)", "no key -> local embedder")

    # ---- Neo4j ----
    if s.use_neo4j:
        try:
            from neo4j import GraphDatabase

            drv = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_username, s.neo4j_password))
            drv.verify_connectivity()
            drv.close()
            line(OK, "Neo4j (graph)", s.neo4j_uri)
        except Exception as e:
            line(FAIL, "Neo4j (graph)", str(e)[:90])
    else:
        line(SKIP, "Neo4j (graph)", "no uri/password -> in-memory graph")

    # ---- Qdrant ----
    if s.use_qdrant:
        try:
            from qdrant_client import QdrantClient

            client = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None)
            cols = client.get_collections()
            line(OK, "Qdrant (vectors)", f"{len(cols.collections)} collection(s)")
        except Exception as e:
            line(FAIL, "Qdrant (vectors)", str(e)[:90])
    else:
        line(SKIP, "Qdrant (vectors)", "no url -> in-memory vectors")

    # ---- Cohere ----
    if s.use_cohere:
        try:
            import cohere

            client = cohere.Client(api_key=s.cohere_api_key)
            client.rerank(
                model=s.cohere_rerank_model, query="bail",
                documents=["bail under CrPC", "murder under IPC"], top_n=1,
            )
            line(OK, "Cohere (rerank)", f"model={s.cohere_rerank_model}")
        except Exception as e:
            line(FAIL, "Cohere (rerank)", str(e)[:90])
    else:
        line(SKIP, "Cohere (rerank)", "no key -> local passthrough")

    # ---- config hygiene ----
    print("-" * 64)
    if s.jwt_secret in ("change-me-in-production", "please-change-this-to-a-long-random-string"):
        line(FAIL, "JWT_SECRET", "still a placeholder — change before deploy")
    else:
        line(OK, "JWT_SECRET", "custom value set")
    if s.admin_password == "admin":
        line(FAIL, "ADMIN_PASSWORD", "still 'admin' — change before deploy")
    else:
        line(OK, "ADMIN_PASSWORD", "custom value set")

    print("=" * 64)
    print("Tip: [skip] is fine — that layer just uses the local fallback.")


if __name__ == "__main__":
    main()
