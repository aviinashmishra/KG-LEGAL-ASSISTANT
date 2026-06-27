"""KG-RAG Legal Assistant — production FastAPI app.

Wires structured logging, request/rate-limit middleware, DB init, observability,
the v1 routers (auth, chat, features, admin, billing), the premium SPA, and
health/readiness probes. Everything runs on local fallbacks with zero credentials.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import admin, auth, billing, chat, features, graph
from app.bootstrap import initialize
from app.config import get_settings
from app.core.logging import get_logger
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.core.observability import init_observability
from app.db.database import init_db
from app.kg.graph_store import get_graph_store

logger = get_logger("kg-legal.app")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("starting KG-RAG Legal Assistant")
    print(settings.provider_banner())
    init_db()
    init_observability()
    # Warm up the graph + indexes in a background thread so the HTTP socket binds
    # immediately. uvicorn opens the listening port only after lifespan startup
    # returns; doing heavy work here would delay binding past the platform's
    # port-scan window (Render/Railway). Requests lazily wait via ensure_initialized().
    import threading

    threading.Thread(
        target=lambda: initialize(verbose=True), name="warmup", daemon=True
    ).start()
    yield


app = FastAPI(
    title="KG-RAG Legal Assistant",
    version="1.0.0",
    description="Knowledge-Graph-powered, citation-grounded legal intelligence for Indian law.",
    lifespan=lifespan,
)

# --- middleware (order: context outermost, then rate limit) ---
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- routers ---
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(features.router)
app.include_router(graph.router)
app.include_router(admin.router)
app.include_router(billing.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    from app.bootstrap import ensure_initialized

    ensure_initialized()
    settings = get_settings()
    store = get_graph_store()
    stats = store.stats()
    ready_flag = stats.get("nodes", 0) > 0
    return {
        "ready": ready_flag,
        "providers": {
            "llm": "anthropic" if settings.use_anthropic else "stub",
            "embeddings": (
                "openai" if settings.use_openai_embeddings
                else "hashing" if settings.use_light_embeddings
                else "local"
            ),
            "graph": store.backend,
            "vectors": "qdrant" if settings.use_qdrant else "in-memory",
            "rerank": "cohere" if settings.use_cohere else "local",
            "cache": "redis" if settings.use_redis else "in-memory",
        },
        "graph_stats": stats,
    }


# --- premium SPA ---
if (WEB_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")


@app.get("/")
def index() -> FileResponse:
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"detail": "SPA not built. See app/web/index.html"}, status_code=404)
