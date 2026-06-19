"""Chat router: query (cached + logged), SSE stream, conversation history."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import run_pipeline_streaming, state_to_response
from app.auth.deps import Principal, current_user, enforce_quota, optional_user
from app.bootstrap import ensure_initialized
from app.db import repo
from app.schemas import QueryRequest, QueryResponse
from app.services.chat_service import answer_query

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, principal: Principal = Depends(enforce_quota)) -> QueryResponse:
    ensure_initialized()
    return answer_query(
        req.query,
        language=req.language,
        user_id=principal.user_id,
        persist=not principal.is_anonymous,
    )


@router.post("/stream")
def stream(req: QueryRequest, principal: Principal = Depends(enforce_quota)) -> EventSourceResponse:
    ensure_initialized()

    def gen():
        final = None
        for event_name, state in run_pipeline_streaming(req.query, language=req.language):
            final = state
            trace = state.get("trace", [])
            msg = trace[-1] if trace else event_name
            yield {"event": "progress", "data": json.dumps({"node": event_name, "message": msg})}
        if final is not None:
            resp = state_to_response(final)
            if not principal.is_anonymous and principal.user_id is not None:
                conv = repo.create_conversation(principal.user_id, title=req.query)
                repo.add_message(conv.id, "user", req.query)
                repo.add_message(
                    conv.id, "assistant", resp.answer,
                    confidence=resp.confidence, hallucination_score=resp.hallucination_score,
                    citations=[c.model_dump() for c in resp.citations],
                    kg_nodes=resp.kg_nodes_traversed,
                )
                resp.conversation_id = conv.id
            yield {"event": "result", "data": resp.model_dump_json()}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(gen())


@router.get("/conversations")
def conversations(principal: Principal = Depends(current_user)) -> list[dict]:
    return [
        {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()}
        for c in repo.list_conversations(principal.user_id)
    ]


@router.get("/conversations/{conversation_id}")
def conversation_messages(conversation_id: int, principal: Principal = Depends(current_user)) -> list[dict]:
    msgs = repo.list_messages(conversation_id)
    return [
        {
            "role": m.role,
            "content": m.content,
            "confidence": m.confidence,
            "citations": json.loads(m.citations_json or "[]"),
            "kg_nodes": json.loads(m.kg_nodes_json or "[]"),
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]


@router.post("/save")
def save_research(payload: dict, principal: Principal = Depends(current_user)) -> dict:
    item = repo.save_research(
        principal.user_id,
        title=payload.get("title", "Untitled"),
        query=payload.get("query", ""),
        answer=payload.get("answer", ""),
        payload=payload.get("payload", {}),
    )
    return {"id": item.id, "status": "saved"}


@router.get("/saved")
def list_saved(principal: Principal = Depends(current_user)) -> list[dict]:
    return [
        {"id": s.id, "title": s.title, "query": s.query, "created_at": s.created_at.isoformat()}
        for s in repo.list_saved(principal.user_id)
    ]
