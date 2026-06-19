"""Sparse BM25 index for exact statute / citation matching (PRD §3.1 Layer 2)."""
from __future__ import annotations

import re
from typing import List

from app.schemas import Document


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


class BM25Index:
    backend = "bm25"

    def __init__(self) -> None:
        self._docs: List[Document] = []
        self._bm25 = None

    def build(self, docs: List[Document]) -> None:
        from rank_bm25 import BM25Okapi

        self._docs = list(docs)
        corpus = [_tokenize(d.text) for d in self._docs]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, top_k: int = 10) -> List[Document]:
        if not self._bm25 or not self._docs:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        out: List[Document] = []
        for i in ranked:
            if scores[i] <= 0:
                continue
            out.append(self._docs[i].model_copy(update={"score": float(scores[i])}))
        return out

    def count(self) -> int:
        return len(self._docs)


_INDEX = BM25Index()


def get_bm25_index() -> BM25Index:
    return _INDEX
