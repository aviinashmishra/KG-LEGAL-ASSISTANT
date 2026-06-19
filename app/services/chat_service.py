"""Chat service: runs the pipeline with caching, query logging, and persistence."""
from __future__ import annotations

import time
from typing import Optional

from app.agents.graph import run_pipeline, state_to_response
from app.config import get_settings
from app.core.cache import cache_key, cached_json_get, cached_json_set
from app.db import repo
from app.schemas import QueryResponse


def answer_query(
    query: str,
    language: str = "en",
    user_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    persist: bool = False,
) -> QueryResponse:
    settings = get_settings()
    key = cache_key("query", language, query.strip().lower())

    cached = cached_json_get(key)
    start = time.perf_counter()
    if cached:
        resp = QueryResponse(**cached)
        resp.cache_hit = True
        cache_hit = True
    else:
        state = run_pipeline(query, language=language)
        resp = state_to_response(state)
        resp.cache_hit = False
        cache_hit = False
        cached_json_set(key, resp.model_dump())

    latency_ms = int((time.perf_counter() - start) * 1000)

    # query log (metrics)
    repo.log_query(
        user_id=user_id,
        query=query,
        intent="",
        confidence=resp.confidence,
        hallucination_score=resp.hallucination_score,
        latency_ms=latency_ms,
        llm_provider="anthropic" if settings.use_anthropic else "stub",
        cache_hit=cache_hit,
    )

    # conversation persistence (logged-in users)
    if persist and user_id is not None:
        if conversation_id is None:
            conv = repo.create_conversation(user_id, title=query)
            conversation_id = conv.id
        repo.add_message(conversation_id, "user", query)
        repo.add_message(
            conversation_id,
            "assistant",
            resp.answer,
            confidence=resp.confidence,
            hallucination_score=resp.hallucination_score,
            citations=[c.model_dump() for c in resp.citations],
            kg_nodes=resp.kg_nodes_traversed,
        )
        resp.conversation_id = conversation_id

    return resp
