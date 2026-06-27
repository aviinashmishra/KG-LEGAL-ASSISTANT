"""Dense vector store.

Qdrant when QDRANT_URL is set; otherwise an in-memory numpy cosine index. Both
expose `upsert` and `search` over the same `Document` schema.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from app.config import get_settings
from app.retrieval.embeddings import Embedder, get_embedder
from app.schemas import Document


class InMemoryVectorStore:
    backend = "in-memory"

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._matrix: Optional[np.ndarray] = None
        self._docs: List[Document] = []

    def upsert(self, docs: List[Document]) -> None:
        if not docs:
            return
        vecs = np.array(self.embedder.embed([d.text for d in docs]), dtype=np.float32)
        vecs = _l2_normalize(vecs)
        self._docs.extend(docs)
        self._matrix = vecs if self._matrix is None else np.vstack([self._matrix, vecs])

    def search(self, query: str, top_k: int = 10) -> List[Document]:
        if self._matrix is None or not self._docs:
            return []
        q = np.array(self.embedder.embed_one(query), dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        scores = self._matrix @ q
        idx = np.argsort(-scores)[:top_k]
        out: List[Document] = []
        for i in idx:
            d = self._docs[int(i)]
            out.append(d.model_copy(update={"score": float(scores[int(i)])}))
        return out

    def count(self) -> int:
        return len(self._docs)


class QdrantVectorStore:
    backend = "qdrant"

    def __init__(self, embedder: Embedder) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        s = get_settings()
        self.embedder = embedder
        self.collection = s.qdrant_collection
        self._client = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None)
        self._ensure_collection(VectorParams(size=embedder.dim, distance=Distance.COSINE))
        self._n = 0

    def _ensure_collection(self, vectors_config) -> None:
        """Create the collection, recreating it if its vector dim no longer matches
        the active embedder (e.g. after switching MiniLM ↔ OpenAI ↔ hashing)."""
        if not self._client.collection_exists(self.collection):
            self._client.create_collection(self.collection, vectors_config=vectors_config)
            return
        try:
            info = self._client.get_collection(self.collection)
            existing = info.config.params.vectors
            existing_dim = getattr(existing, "size", None)
            if existing_dim is not None and existing_dim != vectors_config.size:
                print(
                    f"[vector_store] collection '{self.collection}' dim {existing_dim} != "
                    f"embedder dim {vectors_config.size}; recreating."
                )
                self._client.recreate_collection(self.collection, vectors_config=vectors_config)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[vector_store] could not verify collection dim ({exc}); continuing.")

    def upsert(self, docs: List[Document]) -> None:
        from qdrant_client.models import PointStruct

        if not docs:
            return
        vecs = self.embedder.embed([d.text for d in docs])
        points = [
            PointStruct(
                id=self._n + i,
                vector=vec,
                payload={
                    "doc_id": d.doc_id,
                    "text": d.text,
                    "source_node_id": d.source_node_id,
                    "metadata": d.metadata,
                },
            )
            for i, (d, vec) in enumerate(zip(docs, vecs))
        ]
        self._client.upsert(collection_name=self.collection, points=points)
        self._n += len(points)

    def search(self, query: str, top_k: int = 10) -> List[Document]:
        qvec = self.embedder.embed_one(query)
        if hasattr(self._client, "query_points"):
            # qdrant-client >= 1.10 (search() removed in newer versions)
            hits = self._client.query_points(
                collection_name=self.collection, query=qvec, limit=top_k, with_payload=True
            ).points
        else:  # pragma: no cover - older client
            hits = self._client.search(
                collection_name=self.collection, query_vector=qvec, limit=top_k
            )
        out: List[Document] = []
        for h in hits:
            p = h.payload or {}
            out.append(
                Document(
                    doc_id=p.get("doc_id", str(h.id)),
                    text=p.get("text", ""),
                    source_node_id=p.get("source_node_id"),
                    metadata=p.get("metadata", {}),
                    score=float(h.score),
                )
            )
        return out

    def count(self) -> int:
        return int(self._client.count(self.collection).count)


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


_STORE = None


def get_vector_store(force_new: bool = False):
    global _STORE
    if _STORE is not None and not force_new:
        return _STORE
    settings = get_settings()
    embedder = get_embedder()
    if settings.use_qdrant:
        try:
            _STORE = QdrantVectorStore(embedder)
            return _STORE
        except Exception as exc:  # pragma: no cover
            print(f"[vector_store] Qdrant unavailable ({exc}); using in-memory store.")
    _STORE = InMemoryVectorStore(embedder)
    return _STORE
