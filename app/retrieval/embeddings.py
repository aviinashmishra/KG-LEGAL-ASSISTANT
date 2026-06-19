"""Dense embedding provider.

OpenAI `text-embedding-3-large` when OPENAI_API_KEY is set; otherwise a local
sentence-transformers model. If sentence-transformers itself is unavailable, a
deterministic hashing embedder keeps the pipeline running (lower quality but valid
vectors), so retrieval never hard-fails.
"""
from __future__ import annotations

import hashlib
import math
from typing import List, Optional

from app.config import get_settings


class Embedder:
    dim: int
    name: str

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class OpenAIEmbedder(Embedder):
    def __init__(self) -> None:
        from openai import OpenAI

        s = get_settings()
        self._client = OpenAI(api_key=s.openai_api_key)
        self.name = s.openai_embed_model
        self.dim = 3072 if "3-large" in self.name else 1536

    def embed(self, texts: List[str]) -> List[List[float]]:
        resp = self._client.embeddings.create(model=self.name, input=texts)
        return [d.embedding for d in resp.data]


class LocalEmbedder(Embedder):
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        s = get_settings()
        self.name = s.local_embed_model
        self._model = SentenceTransformer(self.name)
        # method renamed in newer sentence-transformers; support both
        dim_fn = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dim = int(dim_fn())

    def embed(self, texts: List[str]) -> List[List[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


class HashingEmbedder(Embedder):
    """Last-resort deterministic embedder (bag-of-hashed-tokens, L2-normalized)."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = "hashing-fallback"

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _tokenize(text: str) -> List[str]:
    import re

    return re.findall(r"[a-z0-9]+", (text or "").lower())


_EMBEDDER: Optional[Embedder] = None


def get_embedder(force_new: bool = False) -> Embedder:
    global _EMBEDDER
    if _EMBEDDER is not None and not force_new:
        return _EMBEDDER
    settings = get_settings()
    if settings.use_openai_embeddings:
        try:
            _EMBEDDER = OpenAIEmbedder()
            return _EMBEDDER
        except Exception as exc:  # pragma: no cover
            print(f"[embeddings] OpenAI unavailable ({exc}); trying local model.")
    try:
        _EMBEDDER = LocalEmbedder()
        return _EMBEDDER
    except Exception as exc:
        print(f"[embeddings] sentence-transformers unavailable ({exc}); using hashing embedder.")
        _EMBEDDER = HashingEmbedder()
        return _EMBEDDER
