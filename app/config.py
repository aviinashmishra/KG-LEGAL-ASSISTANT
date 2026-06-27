"""Central configuration + provider selection.

Reads settings from environment / `.env` and exposes which provider each layer
should use. The rule is simple: if the credentials for a layer are present we use
the *real* provider; otherwise we transparently fall back to a local implementation
so the whole system runs offline.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SEED_DIR = DATA_DIR / "seed"
PDF_DIR = DATA_DIR / "pdfs"
INDEX_DIR = DATA_DIR / "index"  # persisted local vector index / graph snapshot


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (Anthropic) ---
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-opus-4-8", alias="ANTHROPIC_MODEL")
    anthropic_fast_model: str = Field(
        "claude-haiku-4-5-20251001", alias="ANTHROPIC_FAST_MODEL"
    )

    # --- Embeddings (OpenAI) ---
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    openai_embed_model: str = Field("text-embedding-3-large", alias="OPENAI_EMBED_MODEL")

    # --- Neo4j ---
    neo4j_uri: str = Field("", alias="NEO4J_URI")
    neo4j_username: str = Field("neo4j", alias="NEO4J_USERNAME")
    neo4j_password: str = Field("", alias="NEO4J_PASSWORD")
    neo4j_database: str = Field("neo4j", alias="NEO4J_DATABASE")

    # --- Qdrant ---
    qdrant_url: str = Field("", alias="QDRANT_URL")
    qdrant_api_key: str = Field("", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field("legal_chunks", alias="QDRANT_COLLECTION")

    # --- Cohere ---
    cohere_api_key: str = Field("", alias="COHERE_API_KEY")
    cohere_rerank_model: str = Field(
        "rerank-multilingual-v3.0", alias="COHERE_RERANK_MODEL"
    )

    # --- Local fallback ---
    local_embed_model: str = Field(
        "sentence-transformers/all-MiniLM-L6-v2", alias="LOCAL_EMBED_MODEL"
    )
    # Force the lightweight hashing embedder (skips torch / sentence-transformers).
    # Ideal for small/free hosts (≤512 MB RAM): fast startup, tiny footprint.
    light_embeddings: bool = Field(False, alias="LIGHT_EMBEDDINGS")

    # --- Pipeline tuning ---
    hallucination_max_unverified: float = Field(
        0.10, alias="HALLUCINATION_MAX_UNVERIFIED"
    )
    max_rewrites: int = Field(1, alias="MAX_REWRITES")
    retrieval_top_k: int = Field(8, alias="RETRIEVAL_TOP_K")

    # --- Persistence ---
    database_url: str = Field("", alias="DATABASE_URL")  # blank -> sqlite at data/app.db

    # --- Auth / security ---
    jwt_secret: str = Field("change-me-in-production", alias="JWT_SECRET")
    jwt_expire_minutes: int = Field(60 * 24 * 7, alias="JWT_EXPIRE_MINUTES")
    admin_email: str = Field("admin@kg-legal.ai", alias="ADMIN_EMAIL")
    admin_password: str = Field("admin", alias="ADMIN_PASSWORD")

    # --- Tiers / quotas (queries per day) ---
    quota_free: int = Field(25, alias="QUOTA_FREE")
    quota_pro: int = Field(1000, alias="QUOTA_PRO")
    quota_enterprise: int = Field(100000, alias="QUOTA_ENTERPRISE")

    # --- Rate limiting (per minute, per client) ---
    rate_limit_per_min: int = Field(60, alias="RATE_LIMIT_PER_MIN")

    # --- Cache ---
    cache_ttl_seconds: int = Field(900, alias="CACHE_TTL_SECONDS")
    redis_url: str = Field("", alias="REDIS_URL")  # blank -> in-memory cache/limiter

    # --- Observability ---
    langsmith_api_key: str = Field("", alias="LANGSMITH_API_KEY")
    phoenix_enabled: bool = Field(False, alias="PHOENIX_ENABLED")

    @property
    def resolved_database_url(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        return f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"

    @property
    def use_redis(self) -> bool:
        return bool(self.redis_url.strip())

    # ---------- provider selection ----------
    @property
    def use_anthropic(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    @property
    def use_openai_embeddings(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def use_light_embeddings(self) -> bool:
        return self.light_embeddings and not self.use_openai_embeddings

    @property
    def use_neo4j(self) -> bool:
        return bool(self.neo4j_uri.strip() and self.neo4j_password.strip())

    @property
    def use_qdrant(self) -> bool:
        return bool(self.qdrant_url.strip())

    @property
    def use_cohere(self) -> bool:
        return bool(self.cohere_api_key.strip())

    def provider_banner(self) -> str:
        """Human-readable summary of which providers are active vs fallback."""
        rows = [
            ("LLM", "Anthropic Claude" if self.use_anthropic else "stub (deterministic)"),
            ("Embeddings", "OpenAI" if self.use_openai_embeddings else ("hashing (light)" if self.use_light_embeddings else f"local ({self.local_embed_model.split('/')[-1]})")),
            ("Graph", "Neo4j AuraDB" if self.use_neo4j else "in-memory NetworkX"),
            ("Vectors", "Qdrant" if self.use_qdrant else "in-memory numpy"),
            ("Rerank", "Cohere" if self.use_cohere else "local score passthrough"),
        ]
        width = max(len(name) for name, _ in rows)
        lines = ["KG-RAG Legal Assistant — active providers:"]
        for name, impl in rows:
            lines.append(f"  {name.ljust(width)} : {impl}")
        return "\n".join(lines)


@lru_cache
def get_settings() -> Settings:
    return Settings()
